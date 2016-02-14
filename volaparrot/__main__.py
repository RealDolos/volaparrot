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


from volapi import Room, listen_many

from .constants import *
from .arb import ARBITRATOR
from .handler import ChatHandler
from .commands import Command


# pylint: disable=invalid-name
logger = logging.getLogger("parrot")
# pylint: enable=invalid-name

def parse_args():
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
    parser.add_argument("--debug", dest="debug", action="store_true")
    parser.add_argument("--rooms", dest="feedrooms", type=str, default=None)
    parser.add_argument("--bind", dest="bind", type=str, default=None)
    parser.add_argument("rooms",
                        type=str, nargs="+",
                        help="Rooms to fuck up")
    parser.set_defaults(noparrot=False,
                        uploads=False,
                        exif=False,
                        debug=False,
                        ded=False,
                        shitposting=False,
                        greenmasterrace=False)

    return parser.parse_args()


def setup_room(room, args):
    # login
    if args.passwd and not room.user.logged_in:
        try:
            logger.debug("logging in")
            room.user.login(args.passwd)
        except Exception:
            logger.exception("Failed to login")
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

    # Wire up listeners
    if handler.handlers:
        room.add_listener("chat", handler)
    if handler.file_handlers:
        room.add_listener("file", handler.__call_file__)
    if handler.pulse_handlers:
        mininterval = min(h.interval for h in handler.pulse_handlers)
        room.add_listener("pulse", handler.__call_pulse__)
        ARBITRATOR.start_pulse(room, mininterval)
        logger.info("installed pulse with interval %f", mininterval)
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
            logger.info("listening...")
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
