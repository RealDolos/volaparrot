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
import logging
import warnings

from volapi.arbritrator import ARBITRATOR


__all__ = ["BaseCommand", "Command", "FileCommand", "PulseCommand"]

LOGGER = logging.getLogger(__name__)


class BaseCommand:
    _active = True
    mute = False
    shitposting = False
    handlers = ()

    def __init__(self, room, *args, **kw):
        self.room = room
        self.mute = room.name in kw.get("args").muterooms

        handlers = getattr(self, "handlers", list())
        if isinstance(handlers, str):
            handlers = handlers,
        self._handlers = list(i.casefold() for i in handlers)
        args, kw = kw, args

    def handles(self, cmd):
        return cmd in self._handlers

    @property
    def active(self):
        return self._active and not self.mute

    @active.setter
    def set_active(self, value):
        self._active = value

    @classmethod
    def set_global_active(cls, value):
        cls._active = value

    def post(self, msg, *args, **kw):
        msg = msg.format(*args, **kw)[:300]

        if not self.active:
            LOGGER.info("Swallowed %s", msg)
            return
        self.room.post_chat(msg)

    @staticmethod
    def nonotify(nick):
        return "{}\u2060{}".format(nick[0], nick[1:])

    def call_later(self, delay, callback, *args, **kw):
        # pylint: disable=no-member
        ARBITRATOR.call_later(self.room, delay, callback, *args, **kw)

    def run_process(self, callback, *args):
        # pylint: disable=no-member
        ARBITRATOR.run_process(self.room, callback, *args)


class Command(BaseCommand):
    greens = False

    def __init__(self, *args, **kw):
        self.admins = kw.get("args").admins
        super().__init__(*args, **kw)

    def isadmin(self, msg):
        return msg.logged_in and msg.nick in self.admins

    def allowed(self, msg):
        return not self.greens or msg.logged_in

    def handle_cmd(self, cmd, remainder, msg):
        old = getattr(self, "__call__", None)
        if old:
            warnings.warn("implement handle_cmd", DeprecationWarning)
            return old(cmd, remainder, msg)
        raise NotImplementedError()


class FileCommand(BaseCommand):
    def onfile(self, file):
        raise NotImplementedError()


class PulseCommand(BaseCommand):
    interval = 0

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.last_interval = 0
        if self.interval <= 0:
            raise RuntimeError("No valid interval")

    def check_interval(self, current, interval=1.0):
        result = current >= self.last_interval + interval
        if result:
            self.last_interval = current
        return result

    def onpulse(self, current):
        raise NotImplementedError()
