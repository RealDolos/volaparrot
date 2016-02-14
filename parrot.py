#!/usr/bin/env python3
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
# pylint: disable=bad-continuation,star-args,too-many-lines

import sys
import codecs

# Windows is best OS
if sys.stdout.encoding.casefold() != "utf-8".casefold():
    sys.stdout = codecs.getwriter(sys.stdout.encoding)(
        sys.stdout.buffer, 'replace')
if sys.stderr.encoding.casefold() != "utf-8".casefold():
    sys.stderr = codecs.getwriter(sys.stderr.encoding)(
        sys.stderr.buffer, 'replace')


import asyncio
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
from time import time
from types import MethodType
from uuid import uuid4

import exifread
# pylint: disable=import-error
import isodate
# pylint: enable=import-error
import volapi.volapi as volapi_internal

from volapi import Room
from volapi.arbritrator import call_async, call_sync, ARBITRATOR
from requests import Session
from path import path

from roomstat import roomstat


ADMINFAG = ["RealDolos"]
BLACKFAGS = [i.casefold() for i in (
    "kalyx", "merc", "loliq", "annoying", "bot", "RootBeats", "JEW2FORU")]
OBAMAS = [i.casefold() for i in (
    "counselor", "briseis")]
PARROTFAG = "Parrot"

# pylint: disable=invalid-name
r = Session()
logger = logging.getLogger("parrot")
warning, info, debug = logger.warning, logger.info, logger.debug
error = partial(logger.error, exc_info=True)
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
        hour, minute, sec = [float(v.num) / float(v.den) for v in values]
        return hour + (minute / 60.0) + (sec / 3600.0)


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

@call_sync
def pulse(self, room, interval=0.2):
    debug("pulse for %s is a go!", repr(room))

    @asyncio.coroutine
    def looper():
        info("looping %s %s", repr(room), repr(interval))
        while True:
            nextsleep = asyncio.sleep(interval)
            try:
                if room.connected and room.conn:
                    room.conn.enqueue_data("pulse", time())
                    room.conn.process_queues()
                    if room.connected:
                        yield from nextsleep
            except Exception:
                error("Failed to enqueue pulse")

    asyncio.async(looper(), loop=self.loop)

@call_async
def _call_later(self, room, delay, callback, *args, **kw):
    if not callback:
        return

    def insert():
        if room.connected and room.conn:
            room.conn.enqueue_data("call", [callback, args, kw])
            room.conn.process_queues()

    info("call later scheduled %r %r %r", room, delay, callback)
    self.loop.call_later(delay, insert)

volapi_internal.EVENT_TYPES += "pulse", "call",
ARBITRATOR.start_pulse = MethodType(pulse, ARBITRATOR)
ARBITRATOR.call_later = MethodType(_call_later, ARBITRATOR)


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

    def call_later(self, delay, callback, *args, **kw):
        ARBITRATOR.call_later(self.room, delay, callback, *args, **kw)


class FileCommand(Command):
    def __call__(self, cmd, remainder, msg):
        return False


class PulseCommand(Command):
    interval = 0

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.last_interval = 0
        if self.interval <= 0:
            raise RuntimeError("No valid interval")

    def __call__(self, cmd, remainder, msg):
        return False

    def check_interval(self, current, interval=1.0):
        result = current >= self.last_interval + interval
        if result:
            self.last_interval = current
        return result


def _init_conn():
    conn = sqlite3.connect("phrases2.db")
    conn.isolation_level = None
    conn.execute("CREATE TABLE IF NOT EXISTS phrases ("
                 "phrase TEXT PRIMARY KEY, "
                 "text TEXT, "
                 "locked INT, "
                 "owner TEXT"
                 ")")
    conn.execute("CREATE TABLE IF NOT EXISTS files ("
                 "phrase TEXT PRIMARY KEY, "
                 "id TEXT, "
                 "name TEXT, "
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
        return True


class NiggersCommand(Command):
    handlers = "!niggers"
    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following black gentlemen cannot use this bot: {}",
                  msg.nick, ", ".join(BLACKFAGS))
        return True


class ObamasCommand(Command):
    handlers = "!obamas"
    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following half-black gentlemen can only use this bot "
                  "once every couple of minutes: {}",
                  msg.nick, ", ".join(OBAMAS))
        return True


class AphaCommand(Command):
    hue = {"!auxo": "auxo",
           "!siri": "Siri",
           "!apha": "apha",
           "!merc": "MercWMouthAndOrDeadpoolAndOrFaggotAsswipe"}
    handlers = list(hue.keys())

    gnames = [i.strip() for i in open("greek2.txt") if i.strip()]

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg) or not remainder.strip():
            return False
        name = self.hue.get(cmd.lower(), "apha")
        with Room(self.room.name, random.choice(self.gnames)) as room:
            room.listen(onusercount=lambda x: False)
            room.post_chat("{}, {} wants me to let you know: {}".format(name, msg.nick, remainder))
        return True


class UploadDownloadCommand(DBCommand, Command):
    file = namedtuple("File", ["phrase", "id", "name", "locked", "owner"])
    workingset = dict()

    @staticmethod
    def to_file(data):
        return UploadDownloadCommand.file(*data)

    def get_file(self, phrase):
        phrase = phrase.casefold()
        if not phrase:
            return None
        cur = self.conn.cursor()
        res = cur.execute("SELECT phrase, id, name, locked, owner FROM files "
                             "WHERE phrase = ?",
                             (phrase,)).fetchone()
        return self.to_file(res) if res else res

    def set_file(self, phrase, name, content, locked, owner):
        # pylint: disable=too-many-arguments
        phrase = phrase.casefold()
        if not phrase or not name or not content:
            return None
        newid = None
        while not newid or newid.exists():
            newid = path(str(uuid4()) + ".cuckload")
        with open(newid, "wb") as outp:
            outp.write(content.read() if hasattr(content, "read") else content.encode("utf-8"))
        try:
            cur = self.conn.cursor()
            cur.execute("INSERT OR REPLACE INTO files (phrase, id, name, locked, owner) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (phrase, newid, name, locked, owner))
        except Exception:
            error("Failed to add file")
            try:
                if not newid:
                    raise Exception("huh?")
                newid.unlink()
            except Exception:
                pass

    def unlock_file(self, phrase):
        cur = self.conn.cursor()
        cur.execute("UPDATE files SET locked = 0 WHERE phrase = ?",
                    (phrase.casefold(),))

    def del_file(self, phrase):
        file = self.get_file(phrase)
        if not file:
            return
        cur = self.conn.cursor()
        cur.execute("DELETE FROM files WHERE phrase = ?",
                    (file.phrase,))
        file = path(file.id)
        if file and file.exists():
            try:
                file.unlink()
            except Exception:
                error("Failed to delete %s", file)

    handlers = "!upload", "!download", "!delfile", "!unlockfile"

    def __call__(self, cmd, remainder, msg):
        meth = getattr(self, "cmd_{}".format(cmd[1:]), None)
        return meth(remainder, msg) if meth else False

    def cmd_upload(self, remainder, msg):
        if not self.allowed(msg):
            return False
        remainder = list(i.strip() for i in remainder.split(" ", 1))
        phrase = remainder.pop(0)
        remainder = remainder[0] if remainder else ""
        debug("upload: %s %s", phrase, remainder)
        file = self.get_file(phrase)
        debug("upload: %s", file)
        if not file:
            return False
        fid = self.workingset.get(file.id, None)
        debug("upload: %s", fid)
        fileobj = None
        try:
            fileobj = self.room.filedict[fid]
        except KeyError:
            debug("upload: not found")

        if not fileobj:
            debug("upload: not present")
            with open(file.id, "rb") as filep:
                fid = self.room.upload_file(filep, upload_as=file.name)
            self.workingset[file.id] = fid
        self.post("{}: @{}", remainder or msg.nick, fid)
        return True

    def cmd_download(self, remainder, msg):
        if not self.allowed(msg) or len(msg.files) != 1 or remainder[0] != "@":
            return False

        fid, phrase = list(i.strip() for i in remainder.split(" ", 1))
        debug("download: %s %s", fid, phrase)
        if not fid or not phrase or " " in phrase:
            debug("download: kill %s %s", fid, phrase)
            return False

        admin = self.isadmin(msg)
        existing = self.get_file(phrase)
        if existing and existing.locked and not admin:
            self.post("The file is locked... in lg188's Dutroux replacement "
                      "dungeon, plsnobulli, {}", msg.nick)
            return True

        file = msg.files[0]
        if file.size > 5 << 20:
            self.post("My tiny ahole cannot take such a huge cock, {}", msg.nick)
            return False

        info("download: inserting file %s", file)
        self.set_file(phrase, file.name, r.get(file.url, stream=True).raw, admin, msg.nick)

        if existing:
            try:
                if not existing.id:
                    raise Exception("what")
                path(existing.id).unlink()
            except Exception:
                pass
        self.post("{}: KUK", msg.nick)
        return True

    def cmd_delfile(self, remainder, msg):
        if not self.isadmin(msg):
            self.post("Go rape a MercWMouth, {}", msg.nick)
            return False
        self.del_file(remainder)
        return True

    def cmd_unlockfile(self, remainder, msg):
        if not self.isadmin(msg):
            self.post("Dongo cannot code, {}", msg.nick)
            return False
        self.unlock_file(remainder)
        return True


class DiscoverCommand(DBCommand, Command):
    handlers = "!addroom", "!delroom", "!discover", "!room"

    @staticmethod
    def _stat(room):
        with Room(room, "letest") as remote:
            remote.listen(onusercount=lambda x: False)
            return (remote.title, max(remote.user_count, 0),
                    len(remote.files), remote.config.get("disabled"))

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

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

        limit = None
        if cmd == "!room":
            remainder = remainder.strip()
            if not remainder:
                return False
            limit = remainder
            remainder = None
        nick = remainder or msg.nick

        self.post("{}: {}", nick, self.make(295 - len(nick), limit))
        return True

    def get_rooms(self, limit=None):
        def keyfn(room):
            return (room[2] + 1) * log(max(2, room[3])), room[0]

        cur = self.conn.cursor()
        if limit:
            rooms = sorted(cur.execute("SELECT room, title, users, files FROM rooms "
                                       "WHERE alive = 1 AND room <> ? "
                                       "AND title LIKE ? COLLATE NOCASE",
                                       (self.room.name, "%{}%".format(limit))),
                           key=keyfn, reverse=True)
        else:
            rooms = sorted(cur.execute("SELECT room, title, users, files FROM rooms "
                                       "WHERE alive = 1 AND room <> ?",
                                       (self.room.name,)),
                           key=keyfn, reverse=True)
        return rooms

    @property
    def rooms(self):
        return self.get_rooms()

    def make(self, maxlen, limit):
        rooms = self.get_rooms(limit)
        result = []
        for room, _, users, files in rooms:
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
        self._add_rooms(rooms, self.rooms)
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
            title, users, files, disabled = roomstat(room)
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

class MoarDiscoverCommand(DiscoverCommand, PulseCommand):
    dirty = True
    fid = 0

    interval = 240

    def handles(self, cmd):
        return bool(cmd)

    def onpulse(self, current):
        info("refreshing")
        try:
            cur = self.conn.cursor()
            rooms = cur.execute("SELECT room FROM rooms WHERE alive <> 2 "
                                "ORDER BY RANDOM() LIMIT 5").fetchall()
            for (room,) in rooms:
                try:
                    title, users, files, disabled = roomstat(room)
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
                    cause = (ex and ex.__cause__) or (ex and ex.__context__) or None
                    if cause and "404" in str(cause):
                        code = 2
                    cur.execute("UPDATE rooms SET alive = ? "
                                "WHERE room = ?",
                                (code, room,))
                    error("Failed to stat room, %d", code)
        except Exception:
            error("Failed to refresh rooms")
        finally:
            info("done refreshing")

    def __call__(self, cmd, remainder, msg):
        if cmd == "!fulldiscover":
            if not self.allowed(msg):
                return

            if MoarDiscoverCommand.dirty or \
                    not self.room.filedict.get(MoarDiscoverCommand.fid):
                result = []
                result += "{:>3}  {:10} {:>6} {:>6} {}".format(
                    "#", "Room", "Users", "Files", "Title"),
                for i, (room, title, users, files) in enumerate(self.rooms):
                    result += "{:>3}. {:10} {:>6} {:>6} {}".format(
                        i + 1, room, users, files, title),
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


class RevolverCommand(Command):
    handlers = "!roulette", "!volarette"

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        if not self.active:
            info("Not rolling")
            return
        if msg.nick in ("Counselor", "Brisis"):
            shoot = 6
        else:
            shoot = random.randint(1, 6)
        self.call_later(1, self.room.post_chat, "loading...", is_me=True)
        self.call_later(4, self.room.post_chat, "spinning...", is_me=True)
        self.call_later(7, self.room.post_chat, "cocking...", is_me=True)
        if shoot == 6:
            self.call_later(8, self.post, "BANG, {} is dead", msg.nick)
        else:
            self.call_later(8, self.post, "CLICK, {} is still foreveralone", msg.nick)
        return True


class DiceCommand(Command):
    handlers = "!dice", "!roll"

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        many = 1
        sides = 6
        match = re.match(r"^(\d+)(?:d(\d+))$", remainder)
        if not match and remainder:
            return False
        if match:
            many = int(match.group(1)) or many
            sides = int(match.group(2)) or sides
        if sides <= 1:
            return False
        if many < 1 or many > 10:
            return False
        self.post("Rolled {}".format(sum(random.randint(1, sides) for _ in range(many))))
        return True


class XDanielCommand(Command):
    handlers = "!siberia", "!cyberia"

    def __call__(self, cmd, remainder, msg):
        nick = remainder.strip() or msg.nick
        self.post("{}: Daniel, also Maksim aka Maxim, also Nigredo, "
                  "free APKs for everybody, {}'s friend",
                  nick, self.nonotify("kALyX"))
        return True


class XResponderCommand(PhraseCommand, Command):
    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
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
                self.post("{}: {} was created by the cuck {}",
                          nick, cmd, self.nonotify(phrase.owner or "System"))
                return True

            phrase = self.get_phrase(cmd[1:])
            if phrase:
                self.post("{}: {}", remainder or nick, phrase.text)
                return True

        return self.shitposting and self.shitpost(nick, msg)


    def shitpost(self, nick, msg):
        lmsg = msg.msg.lower()
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
        if ("melina" in lmsg or "meiina" in lmsg or "sunna" in lmsg or
                "milena" in lmsg or "milana" in lmsg):
            self.post("Melina is gross!")
        return False


@lru_cache(128)
def get_text(url):
    return r.get(url).text, time()


@lru_cache(512)
def get_json(url):
    return r.get(url).json()

class XYoutuberCommand(Command):
    description = re.compile(r'itemprop="description"\s+content="(.+?)"')
    duration = re.compile(r'itemprop="duration"\s+content="(.+?)"')
    title = re.compile(r'itemprop="name"\s+content="(.+?)"')
    youtube = re.compile(
        r"https?://(?:www\.)?(?:youtu\.be/\S+|youtube\.com/(?:v|watch|embed)\S+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.youtube.finditer(msg.msg):
            try:
                resp, _ = get_text(url.group(0).strip())
                title = self.title.search(resp)
                if not title:
                    continue
                title = html.unescape(title.group(1).strip())
                if not title:
                    continue
                duration = self.duration.search(resp)
                if duration:
                    duration = str(isodate.parse_duration(duration.group(1)))
                desc = self.description.search(resp)
                desc = None
                if desc:
                    desc = html.unescape(desc.group(1)).strip()
                if "liquid" in msg.nick.lower():
                    self.post("{}: YouNow links are not allowed, you pedo", msg.nick)
                elif duration and desc and msg.nick.lower() not in ("dongmaster", "doc"):
                    self.post("YouTube: {} ({})\n{}", title, duration, desc)
                elif duration:
                    self.post("YouTube: {} ({})", title, duration)
                elif desc:
                    self.post("YouTube: {}\n{}", title, desc)
                else:
                    self.post("YouTube: {}", title)
            except Exception:
                error("youtubed")
        return False


class XLiveleakCommand(Command):
    description = re.compile(r'property="og:description"\s+content="(.+?)"')
    title = re.compile(r'property="og:title"\s+content="(.+?)"')
    liveleak = re.compile(r"http://(?:.+?\.)?liveleak\.com/view\?[\S]+")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.liveleak.finditer(msg.msg):
            try:
                resp, _ = get_text(url.group(0).strip())
                title = self.title.search(resp)
                if not title:
                    continue
                title = html.unescape(title.group(1).strip())
                if not title:
                    continue
                desc = self.description.search(resp)
                if desc:
                    desc = html.unescape(desc.group(1)).strip()
                if desc:
                    self.post("{}\n{}", title, desc)
                else:
                    self.post("{}", title)
            except Exception:
                error("liveleaked")
        return False


class XIMdbCommand(Command):
    imdb = re.compile(r"imdb\.com/title/(tt\d+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.imdb.finditer(msg.msg):
            try:
                resp = get_json(
                    "http://www.omdbapi.com/?i={}&plot=short&r=json".format(url.group(1).strip()))
                debug("%s", resp)
                title = resp.get("Title")
                if not resp.get("Response") == "True" or not title:
                    continue
                sid = resp.get("seriesID")
                if sid:
                    sid = get_json("http://www.omdbapi.com/?i={}&plot=short&r=json".format(sid))
                    try:
                        title = "{} S{:02}E{:02} - {}".format(sid.get("Title"),
                                                              int(resp.get("Season", "0")),
                                                              int(resp.get("Episode", "0")),
                                                              title)
                    except Exception:
                        error("series")
                year = resp.get("Year", "0 BC")
                rating = resp.get("imdbRating", "0.0")
                rated = resp.get("Rated", "?")
                runtime = resp.get("Runtime", "over 9000 mins")
                plot = resp.get("Plot")
                if not plot:
                    self.post("{}\n{}, {}, {}, {}", title, year, rating, rated, runtime)
                else:
                    self.post("{}\n{}, {}, {}, {}\n{}", title, year, rating, rated, runtime, plot)
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
                    self.post("Yes, unfortunately the fag {} is still a staffer", user)
                else:
                    self.post("Yes, {} is still a staffer", user)
            else:
                if user.lower() == "ptc":
                    self.post("Rest in pieces, sweet jewprince")
                elif user.lower() == "liquid":
                    self.post("pls, Liquid will never be a mod")
                else:
                    self.post("{} is not a staffer".format(user))
            return True
        except Exception:
            error("huh?")
            return False


class ExifCommand(FileCommand):

    def onfile(self, file):
        if not self.active:
            return False

        url = file.url
        urll = url.lower()
        if (not urll.endswith(".jpeg") and not urll.endswith(".jpe") and
                not urll.endswith(".jpg") and not urll.endswith(".png")):
            return False
        if file.size > 10 * 1024 * 1024:
            info("Ignoring %s because too large", file)
            return False
        ttldiff = self.room.config["ttl"] - file.time_left
        if ttldiff > 10:
            info("Ignoring %s because too old", file)
            return False

        info("%s %s %d %d %d", file, url, file.size, file.time_left, ttldiff)
        lat, lon, model = gps(r.get(url).content)
        maps = "https://www.google.com/maps?f=q&q=loc:{:.7},{:.7}&t=k&spn=0.5,0.5".format(lat, lon)
        loc = get_json(
            "http://maps.googleapis.com/maps/api/geocode/json?"
            "latlng={:.7},{:.7}&sensor=true&language=en".format(lat, lon))
        loc = {v.get("types")[0]: v.get("formatted_address") for v in loc["results"]}
        useloc = None
        for i in ("street_address", "route", "postal_code",
                  "administrative_area_level_3", "administrative_area_level_2",
                  "locality", "administrative_level_1", "country"):
            useloc = loc.get(i)
            if useloc:
                break
        if not useloc:
            useloc = "Unknown place"
        self.post("@{} {}\nGPS: {}\nModel: {}", file.id, useloc, maps, model)


class CurrentTimeCommand(PulseCommand):
    interval = 60.0

    def onpulse(self, current):
        info("%r: got pulsed %.2f", self.room, current)


class ChatHandler:
    def __init__(self, room, args):
        self.room = room
        self.obamas = dict()

        handlers = list()
        file_handlers = list()
        pulse_handlers = list()
        for cand in globals().values():
            if not inspect.isclass(cand) or not issubclass(cand, Command) \
                    or cand is Command:
                #info("no dice: %s", repr(cand))
                continue
            if args.noparrot and issubclass(cand, PhraseCommand):
                continue
            if not args.uploads and cand is UploadDownloadCommand:
                continue
            if not args.exif and cand is ExifCommand:
                continue
            try:
                if cand is PulseCommand or cand is FileCommand or cand is Command:
                    continue
                inst = cand(room, args.admins)
                handlers += inst,
                if issubclass(cand, FileCommand):
                    file_handlers += inst,
                if issubclass(cand, PulseCommand):
                    pulse_handlers += inst,
            except Exception:
                error("Failed to initialize handler %s", str(cand))
        self.handlers = sorted(handlers, key=repr)
        self.file_handlers = sorted(file_handlers, key=repr)
        self.pulse_handlers = sorted(pulse_handlers, key=repr)
        info("Initialized handlers %s",
             ", ".join(repr(h) for h in self.handlers))
        info("Initialized file handlers %s",
             ", ".join(repr(h) for h in self.file_handlers))
        info("Initialized pulse handlers %s",
             ", ".join(repr(h) for h in self.pulse_handlers))

    def __call__(self, msg):
        info(msg)
        if msg.nick == self.room.user.name:
            return
        lnick = msg.nick.casefold()
        if any(i in lnick for i in BLACKFAGS):
            return
        isObama = any(i in lnick for i in OBAMAS)
        if isObama and self.obamas.get(lnick, 0) + 600 > time():
            info("Ignored Obama %s", lnick)
            return

        cmd = msg.msg.split(" ", 1)
        cmd, remainder = (cmd[0].strip().casefold(),
                          cmd[1].strip() if len(cmd) == 2 else "")
        if not cmd:
            return
        for handler in self.handlers:
            try:
                if handler.handles(cmd) and handler(cmd, remainder, msg):
                    if isObama:
                        self.obamas[lnick] = time()
                    return
            except Exception:
                error("Failed to procss command %s with handler %s",
                      cmd, repr(handler))

    def __call_file__(self, file):
        for handler in self.file_handlers:
            try:
                if handler.onfile(file):
                    return
            except Exception:
                error("Failed to procss command %s with handler %s",
                      file, repr(handler))

    def __call_pulse__(self, current):
        debug("got a pulse: %d", current)
        for handler in self.pulse_handlers:
            try:
                if not handler.check_interval(current, handler.interval):
                    continue
                if handler.onpulse(current):
                    return
            except Exception:
                error("Failed to procss command %s with handler %s",
                      time, repr(handler))

    def __call_call__(self, item):
        callback, args, kw = item
        try:
            callback(*args, **kw)
        except Exception:
            error("Failed to process callback with %r (%r, **%r)",
                callback, args, kw)


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
    parser.add_argument("--uploads", dest="uploads", action="store_true")
    parser.add_argument("--exif", dest="uploads", action="store_true")
    parser.add_argument("--rooms", dest="rooms", type=str, default=None)
    parser.add_argument("room",
                        type=str, nargs=1,
                        help="Room to fuck up")
    parser.set_defaults(noparrot=False,
                        uploads=False,
                        exif=False,
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
                handler = ChatHandler(room, args)
                if args.rooms:
                    rooms = list()
                    with open(args.rooms) as roomp:
                        for i in roomp:
                            try:
                                i, dummy = i.split(" ", 1)
                            except Exception:
                                error("Failed to parse line %s", i)
                                continue
                            if not i:
                                continue
                            rooms += i,
                    rooms = set(rooms)
                    if rooms:
                        class Objectify:
                            def __init__(self, **kw):
                                self.__dict__ = kw
                        handler(Objectify(nick="RealDolos", rooms=rooms, msg=""))
                if handler.handlers:
                    room.add_listener("chat", handler)
                if handler.file_handlers:
                    room.add_listener("file", handler.__call_file__)
                if handler.pulse_handlers:
                    mininterval = min(h.interval for h in handler.pulse_handlers)
                    room.add_listener("pulse", handler.__call_pulse__)
                    ARBITRATOR.start_pulse(room, mininterval)
                    info("installed pulse with interval %f", mininterval)
                room.add_listener("call", handler.__call_call__)
                info("listening...")
                room.listen()

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
    def debug_handler(sig, frame):
        import code
        import traceback

        def printall():
            print("\n*** STACKTRACE - START ***\n", file=sys.stderr)
            code = []
            for threadid, stack in sys._current_frames().items():
                code.append("\n# ThreadID: %s" % threadid)
                for filename, lineno, name, line in traceback.extract_stack(stack):
                    code.append('File: "%s", line %d, in %s' % (filename,
                                                                lineno, name))
                    if line:
                        code.append("  %s" % (line.strip()))

            for line in code:
                print(line, file=sys.stderr)
            print("\n*** STACKTRACE - END ***\n", file=sys.stderr)

        def _exit(num=1):
            sys.exit(num)

        env = {
            "_frame": frame,
            "printall": printall,
            "exit": _exit
            }
        env.update(frame.f_globals)
        env.update(frame.f_locals)

        shell = code.InteractiveConsole(env)
        message = "Signal received : entering python shell.\nTraceback:\n"
        message += ''.join(traceback.format_stack(frame))
        shell.interact(message)


    #override_socket("127.0.0.1")
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s.%(msecs)03d %(threadName)s %(levelname)s %(module)s: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("requests").setLevel(logging.WARNING)

    try:
        import signal
        signal.signal(signal.SIGUSR2, debug_handler)
    except Exception:
        error("failed to setup debugging")

    sys.exit(main())
