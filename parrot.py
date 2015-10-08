#!/usr/bin/env python3.4
"""
The MIT License (MIT)
Copyright © 2015 RealDolos

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
# pylint: disable=missing-docstring,broad-except,too-few-public-methods
# pylint: disable=bad-continuation,star-args

import sys
import codecs

# Windows is best OS
if sys.stdout.encoding.casefold() != "utf-8".casefold():
    sys.stdout = codecs.getwriter(sys.stdout.encoding)(
        sys.stdout.buffer, 'replace')
if sys.stderr.encoding.casefold() != "utf-8".casefold():
    sys.stderr = codecs.getwriter(sys.stderr.encoding)(
        sys.stderr.buffer, 'replace')


import html
import inspect
import logging
import os
import random
import re
import sqlite3

from collections import namedtuple, defaultdict
from functools import partial, lru_cache
from io import BytesIO
from math import log10 as log
from statistics import mean, median, stdev
from threading import Thread
from time import sleep, time

import exifread
import isodate

from volapi import Room
from requests import Session

r = Session()

ADMINFAG = ["RealDolos"]
BLACKFAGS = [i.casefold() for i in ("kalyx", "merc",  "loliq", "annoying", "bot", "RootBeats")]
PARROTFAG = "Parrot"

# pylint: disable=invalid-name
warning, info, debug = logging.warning, logging.info, logging.debug
error = partial(logging.error, exc_info=True)
# pylint: enable=invalid-name


def to_size(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 900.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0

    return "%.1f%s%s" % (num, 'Yi', suffix)


def gps(src):

    class LatStub:
        values = "N"


    class LonStub:
        values = "E"


    def deg(values):
        d, m, s = [float(v.num) / float(v.den) for v in values]
        return d + (m / 60.0) + (s / 3600.0)


    if not hasattr(src, "read"):
        src = BytesIO(src)
    exif = exifread.process_file(src, details=False)
    lat = deg(exif["GPS GPSLatitude"].values)
    if exif.get("GPS GPSLatitudeRef", LatStub()).values != "N":
        lat = 0 - lat
    lon = deg(exif["GPS GPSLongitude"].values)
    if exif.get("GPS GPSLongitudeRef", LonStub()).values != "E":
        lon = 0 - lon
    return (lat, lon,
            "{} {}".format(exif.get("Image Make", "Unknown"),
                           exif.get("Image Model", "Unknown")))


class Command:
    active = True
    shitposting = False
    greens = False

    def __init__(self, room, admins, *args, **kw):
        args, kw = kw, args
        self.room = room
        self.admins = admins
        handlers = getattr(self, "handlers", list())
        if isinstance(handlers, str):
            handlers = handlers,
        self._handlers = list(i.casefold() for i in handlers)

    def handles(self, cmd):
        return cmd in self._handlers

    def post(self, msg, *args, **kw):
        msg = msg.format(*args, **kw)[:300]
        if not self.active:
            info("Swallowed %s", msg)
            return
        self.room.post_chat(msg)

    @staticmethod
    def nonotify(nick):
        return "{}\u2060{}".format(nick[0], nick[1:])

    def isadmin(self, msg):
        return msg.logged_in and msg.nick in self.admins

    def allowed(self, msg):
        return not self.greens or msg.logged_in

class FileCommand(Command):
    pass

def _init_conn():
    conn = sqlite3.connect("phrases2.db")
    conn.isolation_level = None
    conn.execute("CREATE TABLE IF NOT EXISTS phrases ("
                 "phrase TEXT PRIMARY KEY, "
                 "text TEXT, "
                 "locked INT, "
                 "owner TEXT"
                 ")")
    conn.execute("CREATE TABLE IF NOT EXISTS rooms ("
                 "room TEXT PRIMARY KEY, "
                 "title TEXT, "
                 "users INT, "
                 "files INT, "
                 "alive INT DEFAULT 1"
                 ")")
    return conn


class DBCommand:
    conn = _init_conn()


class PhraseCommand(DBCommand):
    phrase = namedtuple("Phrase", ["phrase", "text", "locked", "owner"])
    changed = 0

    @staticmethod
    def to_phrase(data):
        return PhraseCommand.phrase(*data)

    def get_phrase(self, phrase):
        phrase = phrase.casefold()
        if not phrase:
            return None
        cur = self.conn.cursor()
        phrase = cur.execute("SELECT phrase, text, locked, owner FROM phrases "
                             "WHERE phrase = ?",
                             (phrase,)).fetchone()
        return self.to_phrase(phrase) if phrase else phrase

    def set_phrase(self, phrase, text, locked, owner):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO phrases VALUES(?, ?, ?, ?)",
                    (phrase.casefold(), text, 1 if locked else 0, owner))
        PhraseCommand.changed = time()
        info("changed %d", self.changed)

    def unlock_phrase(self, phrase):
        cur = self.conn.cursor()
        cur.execute("UPDATE phrases SET locked = 0 WHERE phrase = ?",
                    (phrase.casefold(),))

    def del_phrase(self, phrase):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM phrases WHERE phrase = ?",
                    (phrase.casefold(),))


class PhrasesUploadCommand(Command, PhraseCommand):
    handlers = "!phrases"
    uploaded = 0
    upload = None

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        valid = self.upload
        if valid:
            valid = {f.id: f for f in self.room.files}.get(valid)
            valid = valid and not valid.expired
        info("valid %s %d %d", valid, self.uploaded, PhraseCommand.changed)
        if not self.upload or self.uploaded < PhraseCommand.changed:
            cur = self.conn.cursor()
            phrases = "\r\n".join("{}|{}".format(*row)
                                  for row in cur.execute("SELECT phrase, text "
                                                         "FROM phrases "
                                                         "ORDER BY phrase"))
            with BytesIO(bytes(phrases, "utf-8")) as upload:
                if self.active:
                    self.upload = self.room.upload_file(upload,
                                                        upload_as="phrases.txt")
                self.uploaded = time()
        self.post("{}: @{}", remainder or msg.nick, self.upload)


class AphaCommand(Command):
    m = {"!auxo": "auxo", "!siri": "Siri", "!apha": "apha", "!merc": "MercWMouthAndOrDeadpoolAndOrFaggotAsswipe"}
    handlers = list(m.keys())

    gnames = [i.strip() for i in open("greek2.txt") if i.strip()]

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg) or not remainder.strip():
            return False
        n = self.m.get(cmd.lower(), "apha")
        with Room(self.room.name, random.choice(self.gnames)) as room:
            room.listen(onusercount=lambda x: False)
            room.post_chat("{}, {} wants me to let you know: {}".format(n, msg.nick, remainder))
        return True

class DiscoverCommand(DBCommand, Command):
    handlers = "!addroom", "!delroom", "!discover"

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._thread = Thread(target=self._refresh, daemon=True)
        self._thread.start()

    @staticmethod
    def _stat(room):
        with Room(room) as remote:
            remote.listen(onusercount=lambda x: False)
            return remote.title, max(remote.user_count - 1, 0), len(remote.files), remote.config.get("disabled")

    def _refresh(self):
        conn = _init_conn()

        while True:
            info("refreshing")
            try:
                cur = conn.cursor()
                rooms = cur.execute("SELECT room FROM rooms WHERE alive <> 2 "
                                    "ORDER BY RANDOM() LIMIT 2").fetchall()
                for (room,) in rooms:
                    try:
                        title, users, files, disabled = self._stat(room)
                        if disabled:
                            warning("Killing disabled room")
                            cur.execute("DELETE FROM rooms WHERE room = ?", (room,))
                        else:
                            info("Updated %s %s", room, title)
                            cur.execute("UPDATE rooms set title = ?, users = ?, files = ?, "
                                        "alive = 1 "
                                        "WHERE room = ?",
                                        (title, users, files, room))
                    except Exception as ex:
                        code = 0
                        cause = (ex and ex.__cause__) or (ex and ex.__context) or None
                        if cause and "404" in str(cause):
                            code = 2
                        cur.execute("UPDATE rooms SET alive = ? "
                                    "WHERE room = ?",
                                    (code, room,))
                        error("Failed to stat room, %d", code)
            except Exception:
                error("Failed to refresh rooms")
            sleep(0.4 * 60)


    def __call__(self, cmd, remainder, msg):
        if cmd == "!addroom":
            if not self.allowed(msg):
                self.post("{}: No rooms for you", msg.nick)
                return True
            if self.add_room(msg):
                self.post("{}: Added moar CP", msg.nick)
                return True
            return False

        if cmd == "!delroom":
            return self.del_room(msg)

        nick = remainder or msg.nick

        self.post("{}: {}", nick, self.make(295 - len(nick)))
        return True

    @property
    def rooms(self):
        cur = self.conn.cursor()
        rooms = sorted(cur.execute("SELECT room, title, users, files FROM rooms "
                                   "WHERE alive = 1 AND room <> ?",
                                   (self.room.name,)),
                       key=lambda x: ((x[2] + 1) * log(max(2, x[3])), x[0]),
                       reverse=True)
        return rooms

    def make(self, maxlen):
        rooms = self.rooms
        result = []
        for room, title, users, files in rooms:
            cur = "#{} ({}/{})".format(room, users, files)
            if len(cur) > maxlen:
                break
            result += cur,
            maxlen -= len(cur) + 1
        if not result:
            return "There are no rooms, there is only kok"
        return " ".join(result)

    def add_room(self, msg):
        if len(msg.rooms) < 1:
            return True

        rooms = list(msg.rooms.keys())
        thread = Thread(target=partial(self._add_rooms, rooms, self.rooms), daemon=True)
        thread.start()
        return True

    def _add_rooms(self, rooms, known):
        for room in rooms:
            self.add_one_room(room, known)

    def add_one_room(self, room, known):
        if room.startswith("#"):
            room = room[1:]
        if room in list(r[0] for r in known):
            info("Room %s already known", room)
            return False

        try:
            info("Stating %s", room)
            title, users, files, disabled = self._stat(room)
            if disabled:
                return False
        except Exception:
            error("Failed to retrieve room info for %s", room)
            return False

        info("Added Room %s with (%d/%d)", room, users, files)
        _init_conn().cursor().execute("INSERT OR REPLACE INTO rooms "
                                       "(room, title, users, files) "
                                       "VALUES(?, ?, ?, ?)",
                                       (room, title, users, files))
        return True

    def del_room(self, msg):
        if not self.isadmin(msg):
            self.post("{}: No rooms for you", msg.nick)
            return True

        if not len(msg.rooms) == 1:
            warning("No room supplied")
            return True

        room = list(msg.rooms.keys())[0]
        if room.startswith("#"):
            room = room[1:]

        self.conn.cursor().execute("DELETE FROM rooms WHERE "
                                   "room = ?",
                                   (room,))
        self.post("{}: Nuked that room", msg.nick)
        return True

class MoarDiscoverCommand(DiscoverCommand):
    dirty = True
    fid = 0

    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        if cmd == "!fulldiscover":
            if not self.allowed(msg):
                return

            if MoarDiscoverCommand.dirty or not self.room.filedict.get(MoarDiscoverCommand.fid):
                result = []
                result += "{:>3}  {:10} {:>6} {:>6} {}".format("#", "Room", "Users", "Files", "Title"),
                for i, (room, title, users, files) in enumerate(self.rooms):
                    result += "{:>3}. {:10} {:>6} {:>6} {}".format(i + 1, room, users, files, title),
                result = "\n".join(result)
                warning("%s", result)
                result = bytes(result, "utf-8")
                if self.active:
                    MoarDiscoverCommand.fid = self.room.upload_file(BytesIO(result),
                                                                    upload_as="rooms.txt")
                MoarDiscoverCommand.dirty = False

            if MoarDiscoverCommand.fid:
                self.post("{}: @{}", remainder or msg.nick, MoarDiscoverCommand.fid)
            return

        if msg.nick.lower() == "chen" or msg.nick.lower() == "fishy":
            return

        if self.add_room(msg):
            MoarDiscoverCommand.dirty = True


class DefineCommand(PhraseCommand, Command):
    handlers = "!define"

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return

        phrase, remainder = list(i.strip() for i in remainder.split(" ", 1))
        if not phrase or not remainder:
            warning("Rejecting empty define")
            return True

        phrase = phrase.casefold()
        if len(phrase) < 3:
            self.post("{}: ur dick is too small", msg.nick)
            return True

        existing = self.get_phrase(phrase)
        admin = self.isadmin(msg)
        if existing and existing.locked and not admin:
            warning("Rejecting logged define for %s", phrase)
            self.post("{}: {} says sodomize yerself!",
                      msg.nick, self.nonotify(self.admins[0]))
            return True

        self.set_phrase(phrase, remainder, admin, msg.nick)
        self.post("{}: KOK", msg.nick)
        return True


class AdminActivateCommand(Command):
    handlers = ".active", ".ded"

    def __call__(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("{}: I don't care about your commands", msg.nick)
            return True
        if cmd == ".ded":
            self.post("Segmentation fault... core dumped")
            Command.active = False
        else:
            Command.active = True
            self.post("Let the spam commence")
        return True


class AdminDefineCommand(PhraseCommand, Command):
    handlers = "!unlock", "!undef"

    def __call__(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("{}: FUCK YOU!", msg.nick)
            return True
        if cmd == "!undef":
            self.del_phrase(remainder)
        elif cmd == "!unlock":
            self.unlock_phrase(remainder)
        self.post("Yes master {}", msg.nick)
        return True


class Stat:
    def __init__(self):
        self.sizes = list()

    def add(self, size):
        self.sizes += size,

    @property
    def rawsize(self):
        return sum(self.sizes)

    @property
    def size(self):
        return to_size(sum(self.sizes))

    @property
    def num(self):
        return len(self.sizes)

    @property
    def min(self):
        return to_size(min(self.sizes))

    @property
    def max(self):
        return to_size(max(self.sizes))

    @property
    def mean(self):
        return to_size(mean(self.sizes))

    @property
    def median(self):
        return to_size(median(self.sizes))

    @property
    def stdev(self):
        return to_size(stdev(self.sizes) if len(self.sizes) > 1 else 0.0)


class RoomStatsCommand(Command):
    handlers = ".roomstats", ".stats", ".typestats", ".extstats"
    types = {"user": lambda user, file: user == file.uploader.casefold(),
             "type": lambda type, file: type == file.type.casefold(),
             "ext": lambda ext, file:
                 os.path.splitext(file.name)[1].casefold() in (ext, "." + ext),
             "name": lambda name, file: name in file.name.casefold()}

    def _gen_filters(self, remainder):
        filters = list()
        for word in remainder.split(" "):
            typ = list(i.strip().casefold() for i in word.split(":", 1))
            if len(typ) == 2:
                typ, word = typ
            else:
                typ, word = "name", typ[0]
            filters += partial(self.types[typ]
                               if typ in self.types
                               else self.types["name"],
                               word),
        return filters

    @staticmethod
    def _count(files):
        counts = defaultdict(Stat)
        types = defaultdict(Stat)
        exts = defaultdict(Stat)
        total = Stat()
        for file in files:
            counts[file.uploader].add(file.size)
            types[file.type.casefold()].add(file.size)
            ext = os.path.splitext(file.name)[1] or "Unknown"
            exts[ext.casefold()].add(file.size)
            total.add(file.size)
        return counts, types, exts, total

    def __call__(self, cmd, remainder, msg):
        if cmd.lower() == ".stats":
            user = list(i.strip() for i in remainder.split(" ", 1))
            user, remainder = user if len(user) == 2 else (user[0], "")
            if not user:
                user = msg.nick
            remainder = "user:{} {}".format(user, remainder)

        filters = self._gen_filters(remainder)
        files = list(f for f in self.room.files
                     if all(fi(f) for fi in filters))
        info("Filtered %d files", len(files))

        counts, types, exts, total = self._count(files)

        if cmd.lower() == ".stats":
            counts = counts.get(user, Stat())
            if not counts.num:
                self.post("{} is a faggot and didn't upload anything.\n"
                          "May he be raped by many blackkoks!", user)
                return True
            self.post("{}: {} files totaling {}\n"
                      "Min: {} / Max: {} / Mean: {} / "
                      "Median: {} / StDev: {}",
                      self.nonotify(user), counts.num, counts.size,
                      counts.min, counts.max, counts.mean,
                      counts.median, counts.stdev)
            return True

        if not total.num:
            if not filters:
                self.post("This room is fucking empty and the people in "
                          "this room are henceforth fucking retards!")
            else:
                self.post("Didn't find anything, soooory")
            return True

        if cmd.lower() == ".typestats":
            counts = types
        elif cmd.lower() == ".extstats":
            counts = exts

        counts = sorted(counts.items(),
                        key=lambda i: (-i[1].rawsize, i[0])
                        )[:10]
        counts = list("#{})\u00a0{}: {} [{}]".
                      format(i + 1, self.nonotify(u), e.size, e.num)
                      for i, (u, e) in enumerate(counts))
        trunc = list()
        total = "{} files totaling {}".format(total.num, total.size)
        rem = 300 - len(total) - 25
        for count in counts:
            if len(count) > rem:
                break
            rem -= len(count)
            trunc += count,
        self.post("{}\n{}",
                  total, ", ".join(trunc))
        return True


class EightballCommand(Command):
    handlers = "!8ball", "!eightball", "!blueballs"

    phrases = [
        "It is certain",
        "It is decidedly so",
        "Without a doubt",
        "Yes definitely",
        "You may rely on it",
        "As I see it, yes",
        "Most likely",
        "Outlook good",
        "Yes",
        "Signs point to yes",
        "Reply hazy try again",
        "Ask again later",
        "Better not tell you now",
        "Cannot predict now",
        "Concentrate and ask again",
        "Don't count on it",
        "My reply is no",
        "My sources say no",
        "Outlook not so good",
        "Very doubtful"
        ]

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        if not remainder.strip():
            self.post("{}: You're a faggot!", msg.nick)
            return True
        self.post("{}: {}", msg.nick, random.choice(self.phrases))
        return True


class XDanielCommand(Command):
    handlers = "!siberia", "!cyberia"

    def __call__(self, cmd, remainder, msg):
        nick = remainder.strip() or msg.nick
        self.post("{}: Daniel, also Maksim aka Maxim, also Nigredo, free APKs for everybody, {}'s friend", nick, self.nonotify("kALyX"))
        return True

class XResponderCommand(PhraseCommand, Command):
    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        lmsg = msg.msg.lower()
        nick = msg.nick

        if cmd.startswith("!"):
            if not self.allowed(msg):
                return False
            if cmd == "!who":
                cmd = (remainder or "").strip()
                if cmd.startswith("!"):
                    cmd = cmd[1:]
                if not cmd:
                    return False
                phrase = self.get_phrase(cmd)
                if not phrase:
                    return False
                self.post("{}: {} was created by the cuck {}", nick, cmd, self.nonotify(phrase.owner or "System"))
                return True
            phrase = self.get_phrase(cmd[1:])
            if phrase:
                self.post("{}: {}", remainder or nick, phrase.text)
                return True

        if not self.shitposting:
            return False

        if lmsg in ("kek", "lel", "lol"):
            self.post("*ʞoʞ")
        if lmsg in ("ay", "ayy", "ayyy", "ayyyy"):
            self.post("lmao")
        if " XD" in msg.msg or msg.msg == "XD":
            self.post("It's lowercase-x-uppercase-D faggot!!!!1!")
        if lmsg in ("topkek",):
            self.post("*topkok")
        if "chateen" in msg.msg or "condorch" in msg.msg:
            self.post("{}: Go away, pedo!", nick)
        if "server prob" in lmsg or (
                ("can't" in lmsg or "cannot" in lmsg or "cant" in lmsg)
                and "download" in lmsg):
            self.post("{}: STFU, nobody in here can do anything about it!",
                      nick)
        if "ALKON" == nick or "ALK0N" == nick or "apha" == nick.lower():
            self.post("STFU newfag m(")
        lmsg = "{} {}".format(nick.lower(), lmsg)
        if "melina" in lmsg or "meiina" in lmsg or "sunna" in lmsg or "milena" in lmsg or "milana" in lmsg:
            self.post("Melina is gross!")
        return False

@lru_cache(128)
def get_text(u):
    return r.get(u).text, time()

@lru_cache(512)
def get_json(u):
    return r.get(u).json()

class XYoutuberCommand(Command):
    description = re.compile(r'itemprop="description"\s+content="(.+?)"')
    duration = re.compile(r'itemprop="duration"\s+content="(.+?)"')
    title = re.compile(r'itemprop="name"\s+content="(.+?)"')
    yt = re.compile(
        r"https?://(?:www\.)?(?:youtu\.be/\S+|youtube\.com/(?:v|watch|embed)\S+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for u in self.yt.finditer(msg.msg):
            try:
                resp, _ = get_text(u.group(0).strip())
                t = self.title.search(resp)
                if not t:
                    continue
                t = html.unescape(t.group(1).strip())
                if not t:
                    continue
                du = self.duration.search(resp)
                if du:
                    du = str(isodate.parse_duration(du.group(1)))
                de = self.description.search(resp)
                de = None
                if de:
                    de = html.unescape(de.group(1)).strip()
                if du and de and msg.nick.lower() not in ("dongmaster", "doc"):
                    self.post("YouTube: {} ({})\n{}", t, du, de)
                elif du:
                    self.post("YouTube: {} ({})", t, du)
                elif de:
                    self.post("YouTube: {}\n{}", t, de)
                else:
                    self.post("YouTube: {}", t)
            except Exception:
                error("youtubed")
        return False

class XLiveleakCommand(Command):
    description = re.compile(r'property="og:description"\s+content="(.+?)"')
    title = re.compile(r'property="og:title"\s+content="(.+?)"')
    ll = re.compile(r"http://(?:.+?\.)?liveleak\.com/view\?[\S]+")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for u in self.ll.finditer(msg.msg):
            try:
                resp, _ = get_text(u.group(0).strip())
                t = self.title.search(resp)
                if not t:
                    continue
                t = html.unescape(t.group(1).strip())
                if not t:
                    continue
                de = self.description.search(resp)
                if de:
                    de = html.unescape(de.group(1)).strip()
                if de:
                    self.post("{}\n{}", t, de)
                else:
                    self.post("{}", t)
            except Exception:
                error("liveleaked")
        return False

class XIMdbCommand(Command):
    imdb = re.compile("imdb\.com/title/(tt\d+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for u in self.imdb.finditer(msg.msg):
            try:
                resp = get_json("http://www.omdbapi.com/?i={}&plot=short&r=json".format(u.group(1).strip()))
                debug("%s", resp)
                title = resp.get("Title")
                if not resp.get("Response") == "True" or not title:
                    continue
                sid = resp.get("seriesID")
                if sid:
                    sid = get_json("http://www.omdbapi.com/?i={}&plot=short&r=json".format(sid))
                    try:
                        title = "{} S{:02}E{:02} - {}".format(sid.get("Title"), int(resp.get("Season", "0")), int(resp.get("Episode", "0")), title)
                    except:
                        error("series")
                year = resp.get("Year", "0 BC")
                rating = resp.get("imdbRating", "0.0")
                rated = resp.get("Rated", "?")
                rt = resp.get("Runtime", "over 9000 mins")
                plot = resp.get("Plot")
                if not plot:
                    self.post("{}\n{}, {}, {}, {}", title, year, rating, rated, rt)
                else:
                    self.post("{}\n{}, {}, {}, {}\n{}", title, year, rating, rated, rt, plot)
            except Exception:
                error("imdbed")
        return False


class ChenCommand(Command):
    def handles(self, cmd):
        if re.match(r"\!che+n$", cmd, re.I):
            return True

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        user = remainder.strip() or msg.nick
        #self.post("{}: H{}NK", user, "O" * min(50, max(1, cmd.lower().count("e"))))
        self.post("{}: M{}RC", user, "E" * min(50, max(1, cmd.lower().count("e"))))
        return True


class CheckModCommand(Command):
    handlers = ":check"

    def __call__(self, cmd, remainder, msg):
        remainder = remainder.strip()
        user = remainder if remainder and " " not in remainder else "MercWMouth"
        info("Getting user %s", user)
        try:
            text, exp = get_text("https://volafile.io/user/{}".format(user))
            if time() - exp > 120:
                get_text.cache_clear()
                get_json.cache_clear()
                text, exp = get_text("https://volafile.io/user/{}".format(user))
            if "Error 404" in text:
                info("Not a user %s", user)
                return False
            i = get_json("https://volafile.io/rest/getUserInfo?name={}".format(user))
            info("Not a user %s", info)
            if i.get("staff"):
                if user.lower() in ("kalyx", "mercwmouth", "davinci", "liquid"):
                    self.post("Yes, unfortunately the fag {} is still a mod", user)
                else:
                    self.post("Yes, {} is still a mod", user)
            else:
                if user.lower() == "ptc":
                    self.post("Rest in pieces, sweet jewprince")
                elif user.lower() == "liquid":
                    self.post("pls, Liquid will never be a mod")
                else:
                    self.post("{} is not a mod".format(user))
            return True
        except Exception:
            error("huh?")
            return False

class ExifCommand(FileCommand):

    def __call__(self, file):
        if not self.active:
            return False

        u = file.url
        ul = u.lower()
        if not ul.endswith(".jpeg") and not ul.endswith(".jpe") and not ul.endswith(".jpg") and not ul.endswith(".png"):
            return False
        if file.size > 10 * 1024 * 1024:
            info("Ignoring %s because too large", file)
            return False
        ttldiff = self.room.config["ttl"] - file.time_left
        if ttldiff > 10:
            info("Ignoring %s because too old", file)
            return False

        info("%s %s %d %d %d", file, u, file.size, file.time_left, ttldiff)
        lat, lon, model = gps(r.get(u).content)
        maps = "https://www.google.com/maps?f=q&q=loc:{:.7},{:.7}&t=k&spn=0.5,0.5".format(lat, lon)
        loc = get_json("http://maps.googleapis.com/maps/api/geocode/json?latlng={:.7},{:.7}&sensor=true&language=en".format(lat, lon))
        loc = {v.get("types")[0]: v.get("formatted_address") for v in loc["results"]}
        useloc = None
        for x in ("street_address", "route", "postal_code", "administrative_area_level_3", "administrative_area_level_2", "locality", "administrative_level_1", "country"):
            useloc = loc.get(x)
            if useloc:
                break
        if not useloc:
            useloc = "Unknown place"
        self.post("@{} {}\nGPS: {}\nModel: {}", file.id, useloc, maps, model)


class ChatHandler:
    def __init__(self, room, admin, noparrot):
        self.room = room
        handlers = list()
        file_handlers = list()
        for cand in globals().values():
            if not inspect.isclass(cand) or not issubclass(cand, Command) \
                    or cand is Command:
                continue
            if noparrot and issubclass(cand, PhraseCommand):
                continue
            try:
                if cand is FileCommand or cand is Command:
                    continue
                if issubclass(cand, FileCommand):
                    file_handlers += cand(room, admin),
                else:
                    handlers += cand(room, admin),
            except Exception:
                error("Failed to initialize handler %s", str(cand))
        self.handlers = sorted(handlers, key=repr)
        self.file_handlers = sorted(file_handlers, key=repr)
        info("Initialized handlers %s",
             ", ".join(repr(h) for h in self.handlers))
        info("Initialized file handlers %s",
             ", ".join(repr(h) for h in self.file_handlers))

    def __call__(self, msg):
        print(msg)
        if msg.nick == self.room.user.name:
            return
        if any(i in msg.nick.casefold() for i in BLACKFAGS):
            return

        cmd = msg.msg.split(" ", 1)
        cmd, remainder = (cmd[0].strip().casefold(),
                          cmd[1].strip() if len(cmd) == 2 else "")
        if not cmd:
            return
        for handler in self.handlers:
            try:
                if handler.handles(cmd) and handler(cmd, remainder, msg):
                    return
            except Exception:
                error("Failed to procss command %s with handler %s",
                      cmd, repr(handler))

    def __call_file__(self, file):
        for handler in self.file_handlers:
            try:
                if handler(file):
                    return
            except Exception:
                error("Failed to procss command %s with handler %s",
                      file, repr(handler))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--parrot", "-p",
                        type=str, default=PARROTFAG,
                        help="Parrot user name")
    parser.add_argument("--admins", "-a", nargs="*",
                        type=str, default=ADMINFAG,
                        help="Admin user name(s)")
    parser.add_argument("--ded", "-d", action="store_true",
                        help="Initially !ded")
    parser.add_argument("--shitposting", action="store_true",
                        help="Let it commence")
    parser.add_argument("--greenmasterrace", action="store_true",
                        help="Only greens can do important stuff")
    parser.add_argument("--passwd",
                        type=str,
                        help="Greenfag yerself")
    parser.add_argument("--no-parrot", dest="noparrot", action="store_true")
    parser.add_argument("--rooms", dest="rooms", type=str, default=None)
    parser.add_argument("room",
                        type=str, nargs=1,
                        help="Room to fuck up")
    parser.set_defaults(noparrot=False,
                        ded=False,
                        shitposting=False,
                        greenmasterrace=False)

    args = parser.parse_args()

    Command.active = not args.ded
    Command.shitposting = args.shitposting
    Command.greens = args.greenmasterrace

    while True:
        try:
            with Room(args.room[0], args.parrot) as room:
                if args.passwd:
                    try:
                        room.user.login(args.passwd)
                    except Exception:
                        error("Failed to login")
                        return 1
                handler = ChatHandler(room, args.admins, args.noparrot)
                if args.rooms:
                    rooms = list()
                    with open(args.rooms) as roomp:
                        for l in roomp:
                            try:
                                l, dummy = l.split(" ", 1)
                            except Exception:
                                error("Failed to parse line %s", l)
                                continue
                            if not l:
                                continue
                            rooms += l,
                    rooms = set(rooms)
                    if rooms:
                        class obj:
                            def __init__(self, **kw):
                                self.__dict__ = kw
                        handler(obj(nick="RealDolos", rooms=rooms, msg=""))
                room.listen(onmessage=handler, onfile=handler.__call_file__)
        except Exception:
            error("Died, respawning")
            sys.exit(1)
    return 0

def override_socket(bind):
    """ Bind all sockets to specific address """
    import socket

    class BoundSocket(socket.socket):
        """
        requests is kinda an asshole when it comes to using source_address.
        Also volapi is also an asshole.
        """

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)

        def connect(self, address):
            try:
                self.bind((bind, 0))
            except Exception:
                pass
            return super().connect(address)

        def connect_ex(self, address):
            try:
                self.bind((bind, 0))
            except Exception:
                pass
            return super().connect_ex(address)

        def bind(self, address):
            super().bind(address)

    socket.socket = BoundSocket


if __name__ == "__main__":
    #override_socket("127.0.0.1")
    logging.basicConfig(level=logging.DEBUG)
    sys.exit(main())
