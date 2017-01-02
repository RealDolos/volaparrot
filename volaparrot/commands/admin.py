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

from .command import Command


__all__ = ["AdminActivateCommand"]

logger = logging.getLogger(__name__)


class AdminActivateCommand(Command):
    handlers = ".active", ".ded"

    def __call__(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("{}: I don't care about your commands", msg.nick)
            return True
        if cmd == ".ded":
            self.post("Segmentation fault... core dumped")
            Command.set_global_active(False)
        else:
            Command.set_global_active(True)
            self.post("Let the spam commence")
        return True
