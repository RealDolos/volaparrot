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
# pylint: disable=bad-continuation,too-many-lines
# pylint: disable=wildcard-import,unused-wildcard-import

import inspect
import logging
import os
import sys

from contextlib import suppress
from importlib import import_module
from time import time
from sqlite3 import Connection

from .constants import *
from .commands import *

# Stuff cwd into python path
sys.path += os.getcwd(),

__all__ = ["Commands", "Handler"]

LOGGER = logging.getLogger(__name__)

MERCDB = Connection("merc.db", isolation_level=None)
MERCDB.cursor().execute("CREATE TABLE IF NOT EXISTS merc (ts INT PRIMARY KEY, msg TEXT)")
MERCDB.cursor().execute("CREATE TABLE IF NOT EXISTS red (ts INT PRIMARY KEY, msg TEXT)")


class Commands(list):
    def __init__(self, additional):
        super().__init__()
        for cmd in additional:
            try:
                mod = import_module(cmd)
                for cand in mod.__dict__.values():
                    if not inspect.isclass(cand) or not issubclass(cand, Command) \
                            or cand is Command:
                        continue
                    self += cand,
            except ImportError:
                LOGGER.exception("Failed to import custom command")
        for cand in globals().values():
            if not inspect.isclass(cand) or not issubclass(cand, Command) \
                    or cand is Command:
                continue
            self += cand,


class Handler:
    def __init__(self, command_candidates, room, args):
        self.room = room
        self.blackfags = args.blacks
        self.obamafags = args.obamas

        self.obamas = dict()

        commands = list()
        file_commands = list()
        pulse_commands = list()
        for cand in command_candidates:
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
                inst = cand(room, args.admins, args=args)
                commands += inst,
                if issubclass(cand, FileCommand):
                    file_commands += inst,
                if issubclass(cand, PulseCommand):
                    pulse_commands += inst,
            except Exception:
                LOGGER.exception("Failed to initialize commands %s", str(cand))

        def sort(cls):
            return cls.__class__.__name__

        self.commands = sorted(commands, key=sort)
        self.file_commands = sorted(file_commands, key=sort)
        self.pulse_commands = sorted(pulse_commands, key=sort)
        LOGGER.debug("Initialized commands %s",
             ", ".join(repr(h) for h in self.commands))
        LOGGER.debug("Initialized file commands %s",
             ", ".join(repr(h) for h in self.file_commands))
        LOGGER.debug("Initialized pulse commands %s",
             ", ".join(repr(h) for h in self.pulse_commands))

    @staticmethod
    def maybe_log(msg, lnick):
        if (lnick == "mercwmouth" and msg.admin) or (lnick == "deadpool" and msg.logged_in):
            MERCDB.cursor().execute(
                "INSERT OR IGNORE INTO merc VALUES (?, ?)",
                (int(time() * 10), msg.msg))
        elif lnick == "red" and msg.admin:
            MERCDB.cursor().execute(
                "INSERT OR IGNORE INTO red VALUES (?, ?)",
                (int(time() * 10), msg.msg))

    def chat(self, msg):
        LOGGER.info("%s %s", self.room.name, msg)
        if msg.nick == self.room.user.name or msg.nick in ("MOTD", "Reminder"):
            return

        lnick = msg.nick.casefold()
        with suppress(IOError):
            Handler.maybe_log(msg, lnick)
        if any(i in lnick for i in self.blackfags):
            return
        if not msg.logged_in and any(i in lnick for i in ("dolos", "doios")):
            return
        is_obama = any(i in lnick for i in self.obamafags)
        if is_obama and self.obamas.get(lnick, 0) + 600 > time():
            LOGGER.info("Ignored Obama %s", lnick)
            return

        cmd = msg.msg.split(" ", 1)
        cmd, remainder = (cmd[0].strip().casefold(),
                          cmd[1].strip() if len(cmd) == 2 else "")
        if not cmd:
            return
        for command in self.commands:
            try:
                if command.handles(cmd) and command(cmd, remainder, msg):
                    if is_obama:
                        self.obamas[lnick] = time()
                    return
            except Exception:
                LOGGER.exception("Failed to procss command %s with command %s",
                      cmd, repr(command))

    def file(self, file):
        for command in self.file_commands:
            try:
                if command.onfile(file):
                    return
            except Exception:
                LOGGER.exception("Failed to procss command %s with command %s",
                      file, repr(command))

    def pulse(self, current):
        LOGGER.debug("got a pulse: %d", current)
        for command in self.pulse_commands:
            try:
                if not command.check_interval(current, command.interval):
                    continue
                if command.onpulse(current):
                    return
            except Exception:
                LOGGER.exception("Failed to procss command %s with command %s",
                      time, repr(command))

    @staticmethod
    def call(item):
        callback, args, kwargs = item
        try:
            callback(*args, **kwargs)
        except Exception:
            LOGGER.exception("Failed to process callback with %r (%r, **%r)",
                callback, args, kwargs)
