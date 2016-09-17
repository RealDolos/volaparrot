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

import logging

from io import BytesIO
from math import log10 as log
from time import time

from volapi import Room

from .command import Command, PulseCommand
from .db import DBCommand
from ..constants import BLACKROOMS, WHITEROOMS
from ..roomstat import roomstat


__all__ = ["DiscoverCommand", "MoarDiscoverCommand"]

logger = logging.getLogger(__name__)


class DiscoverCommand(DBCommand, Command):
    handlers = "!addroom", "!delroom", "!discover", "!room", "!dickover"

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

        if not self.allowed(msg):
            if self.room.name == "6y4jry":
                self.post("{}, drumpie told me to disable this functionality in his room. -- RD", msg.nick)
            else:
                self.post("{}, your mom says to clean up your own room first before you can haz more rooms!", msg.nick)
            return True

        self.post("{}: {}", nick, self.make(295 - len(nick), limit))
        return True

    def get_rooms(self, limit=None):
        def keyfn(room):
            if room[0] in WHITEROOMS:
                return 100000000000, room[0]
            if room[0] in BLACKROOMS:
                return 0, room[0]
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
        rooms = list(rooms)
        for i,r in enumerate(rooms):
            if r[0] == '9pg5Gl':
                rooms[i] = ['9pdLvy',] + list(r[1:])
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
            logger.debug("Room %s already known", room)
            return False

        try:
            logger.info("Stating %s", room)
            title, users, files, disabled = roomstat(room)
            if disabled:
                return False
        except Exception:
            logger.exception("Failed to retrieve room info for %s", room)
            return False

        logger.info("Added Room %s with (%d/%d)", room, users, files)
        self.conn.cursor().execute("INSERT OR IGNORE INTO rooms "
                                       "(room, title, users, files, firstadded) "
                                       "VALUES(?, ?, ?, ?, ?)",
                                       (room, title, users, files, int(time() * 1000)))
        return True

    def del_room(self, msg):
        if not self.isadmin(msg):
            self.post("{}: No rooms for you", msg.nick)
            return True

        if not len(msg.rooms) == 1:
            logger.warning("No room supplied")
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

    interval = 180
    last_check = 0
    refresh_rooms = []

    def handles(self, cmd):
        return bool(cmd)

    def onpulse(self, current):
        if MoarDiscoverCommand.last_check + 120 > time():
            return
        MoarDiscoverCommand.last_check = time()

        logger.debug("refreshing")
        try:
            if not self.refresh_rooms:
                cur = self.conn.cursor()
                self.refresh_rooms = cur.execute("SELECT room FROM rooms WHERE alive <> 2 "
                                    "ORDER BY users DESC, files DESC").fetchall()
            rooms = self.refresh_rooms[:5]
            del self.refresh_rooms[:5]
            for (room,) in rooms:
                cur = self.conn.cursor()
                try:
                    title, users, files, disabled = roomstat(room)
                    if disabled:
                        logger.warning("Killing disabled room")
                        cur.execute("DELETE FROM rooms WHERE room = ?", (room,))
                    else:
                        logger.info("Updated %s %s", room, title)
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
                    logger.exception("Failed to stat room, %d", code)
        except Exception:
            logger.exception("Failed to refresh rooms")
        finally:
            logger.debug("done refreshing")

    def __call__(self, cmd, remainder, msg):
        if cmd == "!fulldiscover":
            if not self.allowed(msg):
                return

            doall = "all" in remainder.lower()

            if MoarDiscoverCommand.dirty or \
                    not self.room.filedict.get(MoarDiscoverCommand.fid):
                result = []
                result += "{:>3}  {:10} {:>6} {:>6} {}".format(
                    "#", "Room", "Users", "Files", "Title"),
                for i, (room, title, users, files) in enumerate(self.rooms):
                    if not doall and not users and not files:
                        continue
                    result += "{:>3}. {:10} {:>6} {:>6} {}".format(
                        i + 1, room, users, files, title),
                result = "\n".join(result)
                logger.warning("%s", result)
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
