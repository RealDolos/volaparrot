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

import logging

from collections import namedtuple
from io import BytesIO
from time import time
from uuid import uuid4

from path import Path

from ..utils import requests
from ..commands.command import Command
from ..commands.db import DBCommand


__all__ = ["UploadDownloadCommand"]

LOGGER = logging.getLogger(__name__)


class UploadDownloadCommand(DBCommand, Command):
    file = namedtuple("File", ["phrase", "id", "name", "locked", "owner"])
    workingset = dict()
    changed = 0
    uploaded = 0
    upload = None

    @staticmethod
    def to_file(data):
        return UploadDownloadCommand.file(*data)

    def get_file(self, phrase):
        phrase = phrase.casefold()
        if not phrase:
            return None
        cur = self.conn.cursor()
        res = cur.execute(
            "SELECT phrase, id, name, locked, owner FROM files "
            "WHERE phrase = ?",
            (phrase,)).fetchone()
        return self.to_file(res) if res else res

    def set_file(self, phrase, name, content, locked, owner):
        # pylint: disable=too-many-arguments
        phrase = phrase.casefold()
        if not phrase or not name or not content:
            return None
        newid = None
        while not newid or newid.exists():
            newid = Path("downloads") / "{!s}.cuckload".format(uuid4())
        newid.parent.mkdir_p()
        with open(newid, "wb") as outp:
            outp.write(content.read() if hasattr(content, "read") else content.encode("utf-8"))
        try:
            cur = self.conn.cursor()
            cur.execute("INSERT OR REPLACE INTO files (phrase, id, name, locked, owner) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (phrase, newid, name, locked, owner))
            UploadDownloadCommand.changed = time()
            LOGGER.debug("changed %d", self.changed)
        except Exception:
            LOGGER.exception("Failed to add file")
            try:
                if not newid:
                    raise Exception("huh?")
                newid.unlink()
            except Exception:
                pass

    def unlock_file(self, phrase):
        cur = self.conn.cursor()
        cur.execute("UPDATE files SET locked = 0 WHERE phrase = ?",
                    (phrase.casefold(),))

    def del_file(self, phrase):
        file = self.get_file(phrase)
        if not file:
            return
        cur = self.conn.cursor()
        cur.execute("DELETE FROM files WHERE phrase = ?",
                    (file.phrase,))
        file = Path(file.id)
        if file and file.exists():
            try:
                file.unlink()
            except Exception:
                LOGGER.exception("Failed to delete %s", file)

    handlers = "!upload", "!download", "!delfile", "!unlockfile", "!files"

    def __call__(self, cmd, remainder, msg):
        meth = getattr(self, "cmd_{}".format(cmd[1:]), None)
        return meth(remainder, msg) if meth else False

    def cmd_upload(self, remainder, msg):
        if not self.allowed(msg):
            return False
        remainder = list(i.strip() for i in remainder.split(" ", 1))
        phrase = remainder.pop(0)
        remainder = remainder[0] if remainder else ""
        LOGGER.debug("upload: %s %s", phrase, remainder)
        file = self.get_file(phrase)
        LOGGER.debug("upload: %s", file)
        if not file:
            return False
        fid = self.workingset.get(file.id, None)
        LOGGER.debug("upload: %s", fid)
        fileobj = None
        try:
            fileobj = self.room.filedict[fid]
        except KeyError:
            LOGGER.debug("upload: not found")

        if not fileobj:
            LOGGER.debug("upload: not present")
            with open(file.id, "rb") as filep:
                fid = self.room.upload_file(filep, upload_as=file.name)
            self.workingset[file.id] = fid
        self.post("{}: @{}", remainder or msg.nick, fid)
        return True

    def cmd_download(self, remainder, msg):
        if not self.allowed(msg) or len(msg.files) != 1 or remainder[0] != "@":
            return False

        fid, phrase = list(i.strip() for i in remainder.split(" ", 1))
        LOGGER.debug("download: %s %s", fid, phrase)
        if not fid or not phrase or " " in phrase:
            LOGGER.debug("download: kill %s %s", fid, phrase)
            return False

        admin = self.isadmin(msg)
        existing = self.get_file(phrase)
        if existing and existing.locked and not admin:
            self.post("The file is locked... in lg188's Dutroux replacement "
                      "dungeon, plsnobulli, {}", msg.nick)
            return True

        file = msg.files[0]
        if file.size > 5 << 20:
            self.post("My tiny ahole cannot take such a huge cock, {}", msg.nick)
            return False

        LOGGER.info("download: inserting file %s", file)
        self.set_file(phrase, file.name, requests.get(file.url, stream=True).raw, admin, msg.nick)

        if existing:
            try:
                if not existing.id:
                    raise Exception("what")
                Path(existing.id).unlink()
            except Exception:
                pass
        self.post("{}: KUK", msg.nick)
        return True

    def cmd_delfile(self, remainder, msg):
        if not self.isadmin(msg):
            self.post("Go rape a MercWMouth, {}", msg.nick)
            return False
        self.del_file(remainder)
        return True

    def cmd_unlockfile(self, remainder, msg):
        if not self.isadmin(msg):
            self.post("Dongo cannot code, {}", msg.nick)
            return False
        self.unlock_file(remainder)
        return True

    def cmd_files(self, remainder, msg):
        if not self.allowed(msg):
            return False
        valid = self.upload
        if valid:
            valid = {f.id: f for f in self.room.files}.get(valid)
            valid = valid and not valid.expired
        LOGGER.debug("valid %s %d", valid, self.uploaded)
        if not self.upload or self.uploaded < self.changed:
            cur = self.conn.cursor()
            phrases = "\r\n".join("{}|{}".format(*row)
                                  for row in cur.execute("SELECT phrase, name "
                                                         "FROM files "
                                                         "ORDER BY phrase"))
            with BytesIO(bytes(phrases, "utf-8")) as upload:
                if self.active:
                    self.upload = self.room.upload_file(upload,
                                                        upload_as="files.txt")
                self.uploaded = time()
        self.post("{}: @{}", remainder or msg.nick, self.upload)
        return True
