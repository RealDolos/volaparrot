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
#pylint: disable=unused-argument

import logging

from time import time
from datetime import datetime, timedelta

from humanize import naturaldelta
from cachetools import LRUCache

from .._version import __version__, __fulltitle__
from ..utils import get_text, get_json
from .command import Command, PulseCommand
from .db import DBCommand


__all__ = [
    "NiggersCommand",
    "ObamasCommand",
    "CheckModCommand",
    "AboutCommand",
    "SeenCommand",
    "AsleepCommand"
    ]

LOGGER = logging.getLogger(__name__)


class NiggersCommand(Command):
    handlers = "!niggers"

    def __init__(self, *args, **kw):
        self.blacks = kw.get("args").blacks
        super().__init__(*args, **kw)

    def handle_niggers(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following black gentlemen cannot use this bot: {}",
                  msg.nick, ", ".join(self.blacks))
        return True


class ObamasCommand(Command):
    handlers = "!obamas"

    def __init__(self, *args, **kw):
        self.obamas = kw.get("args").obamas
        super().__init__(*args, **kw)

    def handle_obamas(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following half-black gentlemen can only use this bot "
                  "once every couple of minutes: {}",
                  msg.nick, ", ".join(self.obamas))
        return True


class CheckModCommand(Command):
    handlers = ":check"

    def staff(self, user):
        if user.lower() in ("mercwmouth",):
            self.post(
                "Yes, unfortunately the literally brown pajeet hitler "
                "and pretend lawyer {} is still a marginally trusted user",
                user)
        elif user.lower() in ("kalyx", "mercwmouth", "davinci", "liquid"):
            self.post(
                "Yes, unfortunately the fag "
                "{} is still a marginally trusted user",
                user)
        else:
            self.post("Yes, {} is still a marginally trusted user", user)

    def admin(self, user):
        if user.lower() in ("mercwmouth",):
            self.post(
                "Yes, unfortunately the literally brown pajeet hitler "
                "and pretend lawyer {} is still a marginally mod user",
                user)
        elif user.lower() in ("kalyx", "mercwmouth", "davinci", "liquid"):
            self.post("Yes, unfortunately the fag {} is still a mod", user)
        elif user.lower() == "ptc":
            self.post("Sweet jewprince is well and alive, unlike Y!erizon")
        else:
            self.post("Yes, {} is still a mod", user)

    def user(self, user):
        if user.lower() in ("mercwmouth",):
            self.post(
                "The literally brown pajeet hitler and pretend lawyer "
                "{} is only a designated user",
                user)
        if user.lower() == "ptc":
            self.post("Rest in pieces, sweet jewprince")
        elif user.lower() == "liquid":
            self.post("pls, Liquid will never be a mod")
        else:
            self.post("{} is not trusted, at all!".format(user))

    def handle_check(self, cmd, remainder, msg):
        remainder = remainder.strip()
        user = remainder if remainder and " " not in remainder else "MercWMouth"
        LOGGER.debug("Getting user %s", user)
        try:
            text, exp = get_text("https://volafile.io/user/{}".format(user))
            if time() - exp > 120:
                get_text.cache_clear()
                get_json.cache_clear()
                text, exp = get_text("https://volafile.io/user/{}".format(user))
            if "Error 404" in text:
                LOGGER.info("Not a user %s", user)
                return False
            i = self.room.conn.make_api_call("getUserInfo", params=dict(name=user))
            if i.get("staff"):
                self.staff(user)
            elif i.get("admin"):
                self.admin(user)
            else:
                self.user(user)
            return True
        except Exception:
            LOGGER.exception("huh?")
            return False


class AboutCommand(Command):
    handlers = "!about", ".about", "!parrot"

    def handle_cmd(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post(
            "{}, I am {}, watch me fly:\n{}",
            remainder or msg.nick,
            __fulltitle__,
            "https://github.com/RealDolos/volaparrot/")
        return True


class SeenCommand(DBCommand, Command, PulseCommand):
    interval = 5 * 60

    seen = LRUCache(maxsize=50)
    start = time()

    usermap = {
        "auxo's waifu": "triggu",
        "doiosodolos": "Daniel",
        "cirno": "Daniel",
        "haskell": "Daniel",
        "ekecheiria": "Daniel",
        "baronbone": "Daniel",
        "cyberia": "Daniel",
        "countcoccyx": "Daniel",
        "doc": "Dongmaster",
        "jewmobile": "TheJIDF",
        "jew": "TheJIDF",
        "thejew": "TheJIDF",
        "mrshlomo": "TheJIDF",
        "pedo": "Counselor",
        "pede": "Counselor",
        "briseis": "Counselor",
        "notnot": "Counselor",
        "counselorpedro": "Counselor",
        "marky": "SuperMarky",
        "mcgill": "SuperMarky",
        "voladolos": "SuperMarky",
        "affarisdolos": "RealDolos",
        "gnuwin7dolos": "RealDolos",
        "cuck": "RealDolos",
        "merc": "MercWMouth",
        "cunt": "MercWMouth",
        "kak": "MercWMouth",
        "dolosodolos": "MODChatBotGladio",
        "fakedolos": "kreg",
        "laindolos": "kreg",
        "fakekreg": "kreg",
        "DaVinci": "Ian",
        "CuckDolos": "Ian",
        "DolosCuck": "Ian",
        "apha": "Polish plebbit pedo",
        "wombatfucker": "NEPTVola",
        }


    def mapname(self, name):
        if name.startswith("Xsa"):
            return "Xsa"
        return self.usermap.get(name.lower(), name)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen ("
                          "user TEXT PRIMARY KEY, "
                          "time INT"
                          ")")
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT time FROM seen ORDER BY time ASC LIMIT 1")
            self.start = int(cur.fetchone()[0]) / 1000
        except Exception:
            LOGGER.exception("Failed to get min seen")


    def handles(self, cmd):
        return True

    def onpulse(self, pulse):
        try:
            LOGGER.info("Dumping seen to db")
            cur = self.conn.cursor()
            cur.executemany(
                "INSERT OR REPLACE INTO seen VALUES(?, ?)",
                list((u, int(v * 1000)) for u, v in self.seen.items())
                )
        except Exception:
            LOGGER.exception("Failed to update seen")

    def handle_cmd(self, cmd, remainder, msg):
        nick = self.mapname(msg.nick).casefold()
        self.seen[nick] = time()
        if msg.admin or msg.staff:
            self.seen["@{}".format(nick)] = time()
        if msg.logged_in:
            self.seen["+{}".format(nick)] = time()

        if cmd != "!seen":
            return False
        if not self.allowed(msg) or not remainder:
            return False

        remainder = remainder.strip()
        remainder = self.mapname(remainder)
        crem = remainder.casefold()
        seen = self.seen.get(crem)
        if not seen:
            cur = self.conn.cursor()
            cur.execute("SELECT time FROM seen WHERE user = ?", (crem,))
            seen = cur.fetchone()
            seen = seen and int(seen[0]) / 1000
        if remainder.lower() == "lain":
            self.post(
                "Lain was never here, will never come here, "
                "and does not care about volafile at all. Please donate!")
        elif not seen:
            self.post(
                "I have not seen {} since {}",
                remainder, naturaldelta(time() - self.start))
        else:
            self.post(
                "{} was last seen {} ago",
                remainder, naturaldelta(time() - seen))
        return True


class AsleepCommand(Command):
    last = None
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def handles(self, cmd):
        return True

    def handle_cmd(self, cmd, remainder, msg):
        if msg.admin and msg.logged_in:
            AsleepCommand.last = datetime.now(), msg.nick
        if cmd != "!asleep":
            return False

        if not AsleepCommand.last:
            self.post("Mods are asleep")
        elif AsleepCommand.last[0] + timedelta(minutes=20) <= datetime.now():
            self.post("Mods have been asleep since {}", naturaldelta(AsleepCommand.last[0]))
        else:
            self.post(
                "{} was awake and trolling {} ago",
                AsleepCommand.last[1],
                naturaldelta(AsleepCommand.last[0]))
        return True
