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
# pylint: disable=redefined-variable-type

try:
    import win_unicode_console
    win_unicode_console.enable(use_unicode_argv=True)
except ImportError:
    pass

import logging
import sys
import time

from contextlib import ExitStack, suppress

from path import Path
from volapi import Room, listen_many

from .constants import ADMINFAG, PARROTFAG
from ._version import __fulltitle__, __version__
from .arb import ARBITRATOR
from .handler import Handler, Commands
from .commands import BaseCommand, Command


# pylint: disable=invalid-name
logger = logging.getLogger("volaparrot.parrot")
# pylint: enable=invalid-name

class Config:
    home = dict()
    curr = dict()

    def __init__(self, name):
        with suppress(Exception):
            self.home = self.init_one(Path("~/.{}.conf".format(name)).expand(), name)
        with suppress(Exception):
            self.curr = self.init_one(Path("./.{}.conf".format(name)).expand(), name)

    @staticmethod
    def init_one(loc, sec):
        from configparser import ConfigParser
        config = ConfigParser()
        config.read(loc)
        return config[sec]

    @staticmethod
    def typed(reqtype, value):
        if reqtype is bool:
            return str(value).lower().strip() in ("yes", "true", "t", "1", "on")
        return reqtype(value)


    def __call__(self, key, default=None, split=None, reqtype=None):
        result = self.curr.get(key, self.home.get(key, default))
        if result is None:
            if reqtype is bool:
                return False
            if split:
                return []
            return result
        if split:
            if reqtype:
                result = [self.typed(reqtype, i) for i in result.split(split)]
            else:
                result = result.split(split)
            return result
        if reqtype:
            return self.typed(reqtype, result)
        return result


def parse_args():
    import argparse

    if len(sys.argv) > 3:
        warning = "wombat detected! Make a .parrot.conf already"
        logger.warning(warning)
        logger.warning(warning.upper())
        logger.warning(warning)
        logger.warning(warning.upper())
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
                        help="Initially .ded")
    parser.add_argument("--shitposting", action="store_true",
                        help="Let it commence")
    parser.add_argument("--greenmasterrace", action="store_true",
                        help="Only greens can do important stuff")
    parser.add_argument("--passwd", default=config("passwd"),
                        type=str,
                        help="Greenfag yerself")
    parser.add_argument("--no-parrot", dest="noparrot", action="store_true",
                        help="Does not actually parrot")
    parser.add_argument("--debug", dest="debug", action="store_true",
                        help="Ignore unless you are dongmaster")
    parser.add_argument("--softlogin", dest="softlogin", action="store_true",
                        help="Allow to continue if login fails (bot will be a whitename)")
    parser.add_argument("--rooms", dest="feedrooms", type=str, default=None,
                        help="Feed the parrot some initial rooms for !discover")
    parser.add_argument("--bind", dest="bind", type=str, default=config("bind"),
                        help="interface to bind to")
    parser.add_argument("--blacks", default=config("blacks", split=" "),
                        type=str, nargs="*",
                        help="Users to ignore")
    parser.add_argument("--obamas", default=config("obamas", split=" "),
                        type=str, nargs="*",
                        help="Users to obama")
    parser.add_argument("--whiterooms", default=config("whiterooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to sanction")
    parser.add_argument("--blackrooms", default=config("blackrooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to downgrade")
    parser.add_argument("--ignoredrooms", default=config("ignoredrooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to completely ignore (in discover)")
    parser.add_argument("--muterooms", default=config("muterooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to lurk bot not spam")
    parser.add_argument("--commands", default=config("commands", split=" "),
                        type=str, nargs="*",
                        help="More commands to use")
    parser.add_argument("rooms", default=config("rooms", split=" "),
                        type=str, nargs="*",
                        help="Rooms to fuck up")
    defaults = {
        "noparrot": False,
        "debug": False,
        "softlogin": False,
        "shitposting": False,
        "greenmasterrace": False,
        }
    parser.set_defaults(**{k: config(k, v, reqtype=bool) for k, v in defaults.items()})
    result = parser.parse_args()
    if not result.rooms:
        parser.error("Provide rooms, you cuck!")
    result.blacks = [i.casefold() for i in result.blacks]
    result.obamas = [i.casefold() for i in result.obamas]
    return result


def setup_room(room, commands, args):
    # login
    if args.passwd and not room.user.logged_in:
        try:
            logger.debug("logging in")
            room.user.login(args.passwd)
        except Exception:
            logger.exception("Failed to login")
            if not args.softlogin:
                return 1
            args.passwd = None
    handler = Handler(commands, room, args)

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
            handler.call(Objectify(nick=ADMINFAG[0], rooms=rooms, msg=""))
        args.feedrooms = None

    # Wire up listeners
    if handler.commands:
        room.add_listener("chat", handler.chat)
    if handler.file_commands:
        room.add_listener("file", handler.file)
    if handler.pulse_commands:
        mininterval = min(h.interval for h in handler.pulse_commands)
        room.add_listener("pulse", handler.pulse)
        ARBITRATOR.start_pulse(room, mininterval)
        logger.debug("installed pulse with interval %f", mininterval)
    room.add_listener("call", handler.call)


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
            with suppress(Exception):
                self.bind((bind, 0))
            return super().connect(address)

        def connect_ex(self, address):
            with suppress(Exception):
                self.bind((bind, 0))
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

    BaseCommand.set_global_active(not args.ded)
    BaseCommand.shitposting = args.shitposting
    Command.greens = args.greenmasterrace

    try:
        commands = Commands(args.commands)
        with ExitStack() as stack:
            rooms = list()
            room0 = None
            for room in args.rooms:
                try:
                    room = stack.enter_context(Room(room, args.parrot, other=room0))
                    if not room0:
                        room0 = room
                    setup_room(room, commands, args)
                    rooms += room,
                    time.sleep(0.5)
                except:
                    logger.error("Failed to connect to room %s", room)
                    raise
            logger.info("%s listening...", __fulltitle__)
            listen_many(*rooms)
    except Exception:
        logger.exception("Died, respawning")
        return 1
    logger.info("bot done")
    return 0


def debug_handler(_, frame):
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

if __name__ == "__main__":
    run()
