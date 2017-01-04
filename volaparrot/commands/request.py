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
# pylint: disable=unused-argument
from datetime import datetime
from io import BytesIO
from time import time

from lru import LRU

from .command import Command


__all__ = ["RequestCommand"]


class RequestCommand(Command):
    handlers = "!request"
    cooldown = LRU(20)
    timeout = 1*60*60

    def handle_request(self, cmd, remainder, msg):
        if not self.active:
            return False
        if self.cooldown.get(msg.nick.lower(), 0) + self.timeout > time():
            self.post("{}, pls wait", msg.nick)
            return True
        data = BytesIO("{} requested this on {}\nEverybody ignored it always".format(
            msg.nick,
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            ).encode("utf-8"))
        name = "[REQUEST] {} - {}".format(remainder.strip(), msg.nick)
        self.room.upload_file(data, upload_as=name)
        self.cooldown[msg.nick.lower()] = time()
        return True
