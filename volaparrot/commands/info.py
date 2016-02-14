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

from time import time

from ..constants import *
from ..utils import get_text, get_json
from .command import Command


__all__ = ["NiggersCommand", "ObamasCommand", "CheckModCommand"]

logger = logging.getLogger(__name__)

class NiggersCommand(Command):
    handlers = "!niggers"
    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following black gentlemen cannot use this bot: {}",
                  msg.nick, ", ".join(BLACKFAGS))
        return True


class ObamasCommand(Command):
    handlers = "!obamas"
    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        self.post("{}, the following half-black gentlemen can only use this bot "
                  "once every couple of minutes: {}",
                  msg.nick, ", ".join(OBAMAS))
        return True


class CheckModCommand(Command):
    handlers = ":check"

    def __call__(self, cmd, remainder, msg):
        remainder = remainder.strip()
        user = remainder if remainder and " " not in remainder else "MercWMouth"
        logger.info("Getting user %s", user)
        try:
            text, exp = get_text("https://volafile.io/user/{}".format(user))
            if time() - exp > 120:
                get_text.cache_clear()
                get_json.cache_clear()
                text, exp = get_text("https://volafile.io/user/{}".format(user))
            if "Error 404" in text:
                logger.info("Not a user %s", user)
                return False
            i = get_json("https://volafile.io/rest/getUserInfo?name={}".format(user))
            if i.get("staff"):
                if user.lower() in ("kalyx", "mercwmouth", "davinci", "liquid"):
                    self.post("Yes, unfortunately the fag {} is still a staffer", user)
                else:
                    self.post("Yes, {} is still a staffer", user)
            else:
                if user.lower() == "ptc":
                    self.post("Rest in pieces, sweet jewprince")
                elif user.lower() == "liquid":
                    self.post("pls, Liquid will never be a mod")
                else:
                    self.post("{} is not a staffer".format(user))
            return True
        except Exception:
            logger.exception("huh?")
            return False


