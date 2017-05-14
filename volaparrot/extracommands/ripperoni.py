"""
The MIT License (MIT)
Copyright © 2017 RealDolos

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
#pylint: disable=unused-argument,missing-docstring

import logging
import tempfile
import os
import threading

from functools import partial
from collections import namedtuple

from path import Path

from volaparrot.commands import Command
from volaparrot.utils import u8str

__all__ = [
    "RipperoniCommand",
    ]

LOGGER = logging.getLogger(__name__)

class RipJob(namedtuple("RipJob", "name, tmp, url")):
    pass

class RipperoniCommand(Command):
    """ Bestest youtube ribba """

    handlers = "!ripperoni",

    def handle_ripperoni(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("No rips for you!")
            return True
        self.run_process(
            partial(self.rip_filename, url=remainder),
            "/usr/bin/env", "youtube-dl",
            "--get-filename", "--ignore-config",
            "-f", "best",
            remainder)
        return True

    def rip_filename(self, res, stdout, stderr, url):
        name = Path(u8str(stdout)).name.strip()
        if res:
            print(res, stdout, stderr)
            self.post("Failed: {}", url)
            return
        self.post("Ripping: {}", name)
        tmpfd, tmp = tempfile.mkstemp(".tmp", "ripperoni", dir=".")
        tmp = Path(tmp)
        os.close(tmpfd)
        job = RipJob(name, tmp, url)
        self.run_process(
            partial(self.ripped, job=job),
            "/usr/bin/env", "youtube-dl",
            "-o", tmp, "--ignore-config", "-c", "--no-part",
            "-f", "best",
            url)

    @staticmethod
    def kill(tmp):
        try:
            tmp.unlink()
        except:
            pass

    def ripped(self, res, stdout, stderr, job):
        if res:
            print(res, stdout, stderr)
            self.kill(job.tmp)
            self.post("Failed: {}", job.url)
            return
        self.post("Uploading: {}", job.name)
        uploader = threading.Thread(target=partial(self.upload, job=job))
        uploader.start()


    def upload(self, job):
        try:
            fid = self.room.upload_file(job.tmp, upload_as=job.name)
            self.call_later(0, self.post_fid, fid, "{} @{}", job.url, fid)
        finally:
            self.kill(job.tmp)

