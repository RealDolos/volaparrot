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

from .command import Command


__all__ = ["EightballCommand", "RevolverCommand", "DiceCommand", "ChenCommand", "XDanielCommand"]

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

