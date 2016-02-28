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


import logging

from contextlib import ExitStack

from path import path
from volapi import Room, listen_many

from .constants import *
from ._version import *
from .arb import ARBITRATOR
from .handler import ChatHandler
from .commands import Command


# pylint: disable=invalid-name
logger = logging.getLogger("volaparrot.parrot")
# pylint: enable=invalid-name

class Config:
    home = dict()
    curr = dict()

    def __init__(self, name):
        try:
            self.home = self.init_one(path("~/.{}.conf".format(name)).expand(), name)
        except Exception:
            pass
        try:
            self.curr = self.init_one(path("./.{}.conf".format(name)).expand(), name)
        except Exception:
            pass

    def init_one(self, loc, sec):
        from configparser import ConfigParser
        config = ConfigParser()
        config.read(loc)
        return config[sec]

    @staticmethod
    def typed(type, value):
        if type is bool:
            return str(value).lower().strip() in ("yes", "true", "t", "1", "on")
        return type(value)


    def __call__(self, key, default=None, split=None, type=None):
        rv = self.curr.get(key, self.home.get(key, default))
        if rv is None:
            if type is bool:
                return False
            return rv
        if split:
            if type:
                rv = [self.typed(type, i) for i in rv.split(split)]
            else:
                rv = rv.split(split)
            return rv
        elif type:
            return self.typed(type, rv)
        return rv


def parse_args():
    import argparse

    config = Config("parrot")
    parser = argparse.ArgumentParser(
        description=__fulltitle__,
        epilog="If you feel the need to use this program, please get your head checked ASAP! "
               "You might have brain cancer!")
    parser.add_argument("--parrot", "-p",
                        type=str, default=config("parrot", PARROTFAG),
                        help="Parrot user name")
    parser.add_argument("--admins", "-a", nargs="*",
                        type=str, default=config("admins", split=" ") or ADMINFAG,
                        help="Admin user name(s)")
    parser.add_argument("--ded", "-d", action="store_true",
                        help="Initially !ded")
    parser.add_argument("--shitposting", action="store_true",
                        help="Let it commence")
    parser.add_argument("--greenmasterrace", action="store_true",
                        help="Only greens can do important stuff")
    parser.add_argument("--passwd", default=config("passwd"),
                        type=str,
                        help="Greenfag yerself")
    parser.add_argument("--no-parrot", dest="noparrot", action="store_true")
    parser.add_argument("--uploads", dest="uploads", action="store_true")
    parser.add_argument("--exif", dest="exif", action="store_true")
    parser.add_argument("--debug", dest="debug", action="store_true")
    parser.add_argument("--softlogin", dest="softlogin", action="store_true")
    parser.add_argument("--rooms", dest="feedrooms", type=str, default=None)
    parser.add_argument("--bind", dest="bind", type=str, default=config("bind"))
    parser.add_argument("rooms", default=config("rooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to fuck up")
    defaults = {
        "noparrot": False,
        "uploads": False,
        "exif": False,
        "debug": False,
        "softlogin": False,
        "shitposting": False,
        "greenmasterrace": False,
        }
    parser.set_defaults(**{k: config(k, v, type=bool) for k,v in defaults.items()})
    rv =  parser.parse_args()
    if not rv.rooms:
        parser.error("Provide rooms, you cuck!")
    return rv


def setup_room(room, args):
    # login
    if args.passwd and not room.user.logged_in:
        try:
            logger.debug("logging in")
            room.user.login(args.passwd)
        except Exception:
            logger.exception("Failed to login")
            if not args.softlogin:
                return 1
    handler = ChatHandler(room, args)

    # XXX Handle elsewhere
    if args.feedrooms:
        rooms = list()
        with open(args.feedrooms) as roomp:
            for i in roomp:
                try:
                    i, dummy = i.split(" ", 1)
                except Exception:
                    logger.exception("Failed to parse line %s", i)
                    continue
                if not i:
                    continue
                rooms += i,
        rooms = set(rooms)
        if rooms:
            class Objectify:
                def __init__(self, **kw):
                    self.__dict__ = kw
            handler(Objectify(nick=ADMINFAG[0], rooms=rooms, msg=""))
        args.feedrooms = None

    # Wire up listeners
    if handler.handlers:
        room.add_listener("chat", handler)
    if handler.file_handlers:
        room.add_listener("file", handler.__call_file__)
    if handler.pulse_handlers:
        mininterval = min(h.interval for h in handler.pulse_handlers)
        room.add_listener("pulse", handler.__call_pulse__)
        ARBITRATOR.start_pulse(room, mininterval)
        logger.debug("installed pulse with interval %f", mininterval)
    room.add_listener("call", handler.__call_call__)


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


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s.%(msecs)03d %(threadName)s %(levelname)s %(module)s: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("requests").setLevel(logging.WARNING)

    logger.info("%s starting up", __fulltitle__)

    oldpw = args.passwd
    try:
        args.passwd = args.passwd and "<redacted>" or None
        logger.info("config: %r", args)
    finally:
        args.passwd = oldpw

    if args.bind:
        override_socket(args.bind)

    Command.active = not args.ded
    Command.shitposting = args.shitposting
    Command.greens = args.greenmasterrace

    try:
        with ExitStack() as stack:
            rooms = list()
            for room in args.rooms:
                room = stack.enter_context(Room(room, args.parrot))
                setup_room(room, args)
                rooms += room,
            logger.info("%s listening...", __fulltitle__)
            listen_many(*rooms)
    except Exception:
        logger.exception("Died, respawning")
        return 1
    logger.info("bot done")
    return 0


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


def run():
    try:
        import signal
        signal.signal(signal.SIGUSR2, debug_handler)
    except Exception:
        logger.exception("failed to setup debugging")

    try:
        sys.exit(main())
    except Exception:
        logger.exception("exited abnormally")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.error("User canceled")
        sys.exit(1)
