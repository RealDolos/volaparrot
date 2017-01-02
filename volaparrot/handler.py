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
# pylint: disable=wildcard-import,unused-wildcard-import

import inspect
import logging

from time import time
from sqlite3 import Connection

from .constants import *
from .commands import *


__all__ = ["ChatHandler"]

logger = logging.getLogger(__name__)

mercdb = Connection("merc.db", isolation_level=None)
mercdb.cursor().execute("CREATE TABLE IF NOT EXISTS merc (ts INT PRIMARY KEY, msg TEXT)")
mercdb.cursor().execute("CREATE TABLE IF NOT EXISTS red (ts INT PRIMARY KEY, msg TEXT)")


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
                logger.exception("Failed to initialize handler %s", str(cand))

        def sort(cls):
            return cls.__class__.__name__

        self.handlers = sorted(handlers, key=sort)
        self.file_handlers = sorted(file_handlers, key=sort)
        self.pulse_handlers = sorted(pulse_handlers, key=sort)
        logger.debug("Initialized handlers %s",
             ", ".join(repr(h) for h in self.handlers))
        logger.debug("Initialized file handlers %s",
             ", ".join(repr(h) for h in self.file_handlers))
        logger.debug("Initialized pulse handlers %s",
             ", ".join(repr(h) for h in self.pulse_handlers))

    def __call__(self, msg):
        logger.info("%s %s", self.room.name, msg)
        if msg.nick == self.room.user.name:
            return
        if msg.nick == "MOTD" and msg.admin:
            return
        lnick = msg.nick.casefold()
        if (lnick == "mercwmouth" and msg.admin) or (lnick == "deadpool" and msg.logged_in):
            mercdb.cursor().execute(
                "INSERT OR IGNORE INTO merc VALUES (?, ?)",
                (int(time() * 10), msg.msg))
        elif lnick == "red" and msg.admin:
            mercdb.cursor().execute(
                "INSERT OR IGNORE INTO red VALUES (?, ?)",
                (int(time() * 10), msg.msg))
        if any(i in lnick for i in BLACKFAGS):
            return
        if not msg.logged_in and any(i in lnick for i in ("dolos", "doios")):
            return
        is_obama = any(i in lnick for i in OBAMAS)
        if is_obama and self.obamas.get(lnick, 0) + 600 > time():
            logger.info("Ignored Obama %s", lnick)
            return

        cmd = msg.msg.split(" ", 1)
        cmd, remainder = (cmd[0].strip().casefold(),
                          cmd[1].strip() if len(cmd) == 2 else "")
        if not cmd:
            return
        for handler in self.handlers:
            try:
                if handler.handles(cmd) and handler(cmd, remainder, msg):
                    if is_obama:
                        self.obamas[lnick] = time()
                    return
            except Exception:
                logger.exception("Failed to procss command %s with handler %s",
                      cmd, repr(handler))

    def __call_file__(self, file):
        for handler in self.file_handlers:
            try:
                if handler.onfile(file):
                    return
            except Exception:
                logger.exception("Failed to procss command %s with handler %s",
                      file, repr(handler))

    def __call_pulse__(self, current):
        logger.debug("got a pulse: %d", current)
        for handler in self.pulse_handlers:
            try:
                if not handler.check_interval(current, handler.interval):
                    continue
                if handler.onpulse(current):
                    return
            except Exception:
                logger.exception("Failed to procss command %s with handler %s",
                      time, repr(handler))

    def __call_call__(self, item):
        callback, args, kw = item
        try:
            callback(*args, **kw)
        except Exception:
            logger.exception("Failed to process callback with %r (%r, **%r)",
                callback, args, kw)


