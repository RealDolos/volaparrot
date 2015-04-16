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

import logging
import inspect
import sqlite3
import os
import sys

from collections import namedtuple, defaultdict
from functools import partial
from math import log2
from statistics import mean, median, stdev
from threading import Thread
from time import sleep

from volapi import Room

ADMINFAG = ["RealDolos"]
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
                 "users INT, "
                 "files INT, "
                 "alive INT DEFAULT 1"
                 ")")
    return conn


class DBCommand:
    conn = _init_conn()


class PhraseCommand(DBCommand):
    phrase = namedtuple("Phrase", ["phrase", "text", "locked"])

    @staticmethod
    def to_phrase(data):
        return PhraseCommand.phrase(*data)

    def get_phrase(self, phrase):
        phrase = phrase.casefold()
        if not phrase:
            return None
        cur = self.conn.cursor()
        ph = cur.execute("SELECT phrase, text, locked FROM phrases "
                         "WHERE phrase = ?",
                         (phrase,)).fetchone()
        return self.to_phrase(ph) if ph else ph

    def set_phrase(self, phrase, text, locked, owner):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO phrases VALUES(?, ?, ?, ?)",
                    (phrase.casefold(), text, 1 if locked else 0, owner))

    def unlock_phrase(self, phrase):
        cur = self.conn.cursor()
        cur.execute("UPDATE phrases SET locked = 0 WHERE phrase = ?",
                    (phrase.casefold(),))


class DiscoverCommand(DBCommand, Command):
    handlers = "!addroom", "!delroom", "!discover"

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._thread = Thread(target=self._refresh, daemon=True)
        self._thread.start()

    def _stat(self, room):
        with Room(room) as remote:
            remote.listen(onusercount=lambda x: False)
            return max(remote.user_count - 1, 0), len(remote.files)

    def _refresh(self):
        conn = _init_conn()

        while True:
            info("refreshing")
            try:
                cur = conn.cursor()
                rooms = cur.execute("SELECT room FROM rooms "
                                    "ORDER BY RANDOM() LIMIT 4").fetchall()
                for (room,) in rooms:
                    try:
                        users, files = self._stat(room)
                        cur.execute("UPDATE rooms set users = ?, files = ?, "
                                    "alive = 1 "
                                    "WHERE room = ?",
                                    (users, files, room))
                    except Exception:
                        cur.execute("UPDATE rooms SET alive = 0 "
                                    "WHERE room = ?",
                                    (room,))
                        error("Failed to stat room")
            except Exception:
                error("Failed to refresh rooms")

            sleep(2 * 60)

    def __call__(self, cmd, remainder, msg):
        if cmd == "!addroom":
            return self.add_room(msg)

        if cmd == "!delroom":
            return self.del_room(msg)

        nick = remainder or msg.nick
        if self.allowed(msg):
            self.post("{}: {}", nick, self.make(295 - len(nick)))
        return True

    def make(self, maxlen):
        cur = self.conn.cursor()
        rooms = sorted(cur.execute("SELECT room, users, files FROM rooms "
                                   "WHERE alive <> 0 AND room <> ?",
                                   (self.room.name,)),
                       key=lambda x: x[1] * log2(max(1, x[2])),
                       reverse=True)
        result = []
        for room, users, files in rooms:
            cur = "#{} ({}/{})".format(room, users, files)
            if len(cur) > maxlen:
                break
            result += cur,
            maxlen -= len(cur) + 1
        if not result:
            return "There are no rooms, there is only kok"
        return " ".join(result)

    def add_room(self, msg):
        if not self.allowed(msg):
            self.post("{}: No rooms for you", msg.nick)
            return True

        if not len(msg.rooms) == 1:
            warning("No room supplied")
            return True

        room = list(msg.rooms.keys())[0]
        if room.startswith("#"):
            room = room[1:]

        try:
            users, files = self._stat(room)
        except Exception:
            error("Failed to retrieve room info for %s", room)
            self.post("{}: Invalid room you cuck", msg.nick)
            return True

        info("Added Room %s with (%d/%d)", room, users, files)
        self.conn.cursor().execute("INSERT OR REPLACE INTO rooms "
                                   "(room, users, files) "
                                   "VALUES(?, ?, ?)",
                                   (room, users, files))
        self.post("{}: Added moar CP", msg.nick)
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


class AdminUnlockCommand(PhraseCommand, Command):
    handlers = "!unlock"

    def __call__(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("{}: FUCK YOU!", msg.nick)
            return True
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
        return to_size(stdev(self.sizes))


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


class XResponderCommand(PhraseCommand, Command):
    def handles(self, cmd):
        yield bool(cmd)

    def __call__(self, cmd, remainder, msg):
        lmsg = msg.msg.lower()
        nick = msg.nick

        if cmd.startswith("!"):
            phrase = self.get_phrase(cmd[1:])
            if phrase:
                self.post("{}: {}", remainder or nick, phrase.text)
                return

        if not self.shitposting:
            return

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
        if "ALKON" == nick or "ALK0N" == nick:
            self.post("STFU newfag m(")


class ChatHandler:
    def __init__(self, room, admin, noparrot):
        self.room = room
        handlers = list()
        for cand in globals().values():
            if not inspect.isclass(cand) or not issubclass(cand, Command) \
                    or cand is Command:
                continue
            if noparrot and issubclass(cand, PhraseCommand):
                continue
            try:
                handlers += cand(room, admin),
            except Exception:
                error("Failed to initialize handler %s", str(cand))
        self.handlers = sorted(handlers, key=repr)
        info("Initialized handlers %s",
             ", ".join(repr(h) for h in self.handlers))

    def __call__(self, msg):
        if msg.nick == self.room.user.name:
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
                room.listen(onmessage=handler)
        except Exception:
            error("Died, respawning")
    return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sys.exit(main())
