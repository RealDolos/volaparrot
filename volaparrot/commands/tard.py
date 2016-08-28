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
import random
import re

from subprocess import Popen, PIPE
from sqlite3 import Connection

from lru import LRU

from .command import Command


__all__ = [
    "EightballCommand",
    "RevolverCommand",
    "DiceCommand",
    "ChenCommand",
    "XDanielCommand",
    "RedardCommand",
    ]

logger = logging.getLogger(__name__)

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
        if "mod" in remainder.lower():
            self.post("{}:The only true mod is VolaMerc 2.0!", msg.nick)
            return True
        self.post("{}: {}", msg.nick, random.choice(self.phrases))
        return True


class RevolverCommand(Command):
    handlers = "!roulette", "!volarette"

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        if not self.active:
            logger.info("Not rolling")
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
        elif shoot == 5:
            self.call_later(8, self.post, "{}, you missed but still managed to hit Counselor.\nCongrats, you killed a pede!", msg.nick)
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

class ProfanityCommand(Command):
    extract = re.compile(r"1:.*?\s+warning\s+(.*?)\s\S+$")
    handlers = "!analyze", "!sjw", "!profanity"
    lru = LRU(20)

    def handles(self, cmd):
        return True

    @staticmethod
    def alex(string):
        with Popen("alex -t".split(" "), stdout=PIPE, stdin=PIPE) as process:
            try:
                string = string.encode("utf-8")
                rv = str(process.communicate(string, timeout=3)[0], "utf-8").split("\n")
            except TimeoutExpired:
                process.kill()
                raise
        rv = (ProfanityCommand.extract.search(l.strip()) for l in rv)
        rv = set(m.group(1).strip() for m in rv if m)
        return rv

    def __call__(self, cmd, remainder, msg):
        if cmd not in self.handlers:
            self.lru[msg.nick.casefold()] = (msg.nick, msg.msg)
            return False

        if not self.allowed(msg):
            return False
        try:
            if remainder:
                user = remainder.strip().casefold()
                user, text = self.lru.get(user, (None, None))
            else:
                user, text = self.lru.items()[0][1]
            if not text:
                return False
            anal = ", ".join(self.alex(text))
            if not anal:
                anal = "No issues found, SJW approved message"
            lanal = len(anal)
            if lanal > 220:
                anal = anal[0:219] + "…"
                lanal = len(anal)
            lrem = 295 - lanal
            quote = ">{user}: {text}".format(user=user, text=text)
            if len(quote) > lrem:
                quote = quote[0:lrem] + "…"
            self.post("{}\n{}", quote, anal)
            return True

        except Exception:
            logger.exception("failed to analyze")
            return False

class RedardCommand(Command):
    redard = re.compile(r"\bredard\b", re.I)
    db = Connection("merc.db", isolation_level=None)

    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        if not self.redard.search(msg.msg):
            return False
        cur = self.db.cursor()
        cur.execute("SELECT msg FROM red ORDER BY RANDOM() LIMIT 1")
        quote = cur.fetchone()
        if not quote:
            return False
        self.post(">Red: {}", quote[0])
        return True

try:
    if "profane" not in "".join(ProfanityCommand.alex("you're a gay")):
        raise Exception("Not found")
    __all__ += "ProfanityCommand",
except Exception:
    logger.warning("Cannot use alex, ProfanityCommand is not available")


if __name__ == "__main__":
    print(ProfanityCommand.alex("you're a gay"))
