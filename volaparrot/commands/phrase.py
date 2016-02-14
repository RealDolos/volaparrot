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

from collections import namedtuple
from io import BytesIO
from time import time

from .command import Command
from .db import DBCommand


__all__ = ["PhraseCommand", "AdminDefineCommand", "DefineCommand", "PhrasesUploadCommand",
           "XResponderCommand"]

logger = logging.getLogger(__name__)


class PhraseCommand(DBCommand):
    phrase = namedtuple("Phrase", ["phrase", "text", "locked", "owner"])
    changed = 0

    @staticmethod
    def to_phrase(data):
        return PhraseCommand.phrase(*data)

    def get_phrase(self, phrase):
        phrase = phrase.casefold()
        if not phrase:
            return None
        cur = self.conn.cursor()
        phrase = cur.execute("SELECT phrase, text, locked, owner FROM phrases "
                             "WHERE phrase = ?",
                             (phrase,)).fetchone()
        return self.to_phrase(phrase) if phrase else phrase

    def set_phrase(self, phrase, text, locked, owner):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO phrases VALUES(?, ?, ?, ?)",
                    (phrase.casefold(), text, 1 if locked else 0, owner))
        PhraseCommand.changed = time()
        logger.info("changed %d", self.changed)

    def unlock_phrase(self, phrase):
        cur = self.conn.cursor()
        cur.execute("UPDATE phrases SET locked = 0 WHERE phrase = ?",
                    (phrase.casefold(),))

    def del_phrase(self, phrase):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM phrases WHERE phrase = ?",
                    (phrase.casefold(),))


class AdminDefineCommand(PhraseCommand, Command):
    handlers = "!unlock", "!undef"

    def __call__(self, cmd, remainder, msg):
        if not self.isadmin(msg):
            self.post("{}: FUCK YOU!", msg.nick)
            return True
        if cmd == "!undef":
            self.del_phrase(remainder)
        elif cmd == "!unlock":
            self.unlock_phrase(remainder)
        self.post("Yes master {}", msg.nick)
        return True


class DefineCommand(PhraseCommand, Command):
    handlers = "!define"

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return

        phrase, remainder = list(i.strip() for i in remainder.split(" ", 1))
        if not phrase or not remainder:
            logger.warning("Rejecting empty define")
            return True

        phrase = phrase.casefold()
        if len(phrase) < 3:
            self.post("{}: ur dick is too small", msg.nick)
            return True

        existing = self.get_phrase(phrase)
        admin = self.isadmin(msg)
        if existing and existing.locked and not admin:
            logger.warning("Rejecting logged define for %s", phrase)
            self.post("{}: {} says sodomize yerself!",
                      msg.nick, self.nonotify(self.admins[0]))
            return True

        self.set_phrase(phrase, remainder, admin, msg.nick)
        self.post("{}: KOK", msg.nick)
        return True


class PhrasesUploadCommand(Command, PhraseCommand):
    handlers = "!phrases"
    uploaded = 0
    upload = None

    def __call__(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return True
        valid = self.upload
        if valid:
            valid = {f.id: f for f in self.room.files}.get(valid)
            valid = valid and not valid.expired
        logger.info("valid %s %d %d", valid, self.uploaded, PhraseCommand.changed)
        if not self.upload or self.uploaded < PhraseCommand.changed:
            cur = self.conn.cursor()
            phrases = "\r\n".join("{}|{}".format(*row)
                                  for row in cur.execute("SELECT phrase, text "
                                                         "FROM phrases "
                                                         "ORDER BY phrase"))
            with BytesIO(bytes(phrases, "utf-8")) as upload:
                if self.active:
                    self.upload = self.room.upload_file(upload,
                                                        upload_as="phrases.txt")
                self.uploaded = time()
        self.post("{}: @{}", remainder or msg.nick, self.upload)
        return True


class XResponderCommand(PhraseCommand, Command):
    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        nick = msg.nick

        if cmd.startswith("!"):
            if not self.allowed(msg):
                return False
            if cmd == "!who":
                cmd = (remainder or "").strip()
                if cmd.startswith("!"):
                    cmd = cmd[1:]
                if not cmd:
                    return False
                phrase = self.get_phrase(cmd)
                if not phrase:
                    return False
                self.post("{}: {} was created by the cuck {}",
                          nick, cmd, self.nonotify(phrase.owner or "System"))
                return True

            phrase = self.get_phrase(cmd[1:])
            if phrase:
                self.post("{}: {}", remainder or nick, phrase.text)
                return True

        return self.shitposting and self.shitpost(nick, msg)


    def shitpost(self, nick, msg):
        lmsg = msg.msg.lower()
        if lmsg in ("kek", "lel", "lol"):
            self.post("*ʞoʞ")
        if lmsg in ("ay", "ayy", "ayyy", "ayyyy"):
            self.post("lmao")
        if " XD" in msg.msg or msg.msg == "XD":
            self.post("It's lowercase-x-uppercase-D faggot!!!!1!")
        if lmsg in ("topkek",):
            self.post("*topkok")
        if "chateen" in msg.msg or "condorch" in msg.msg:
            self.post("{}: Go away, pedo!", nick)
        if "server prob" in lmsg or (
                ("can't" in lmsg or "cannot" in lmsg or "cant" in lmsg)
                and "download" in lmsg):
            self.post("{}: STFU, nobody in here can do anything about it!",
                      nick)
        if "ALKON" == nick or "ALK0N" == nick or "apha" == nick.lower():
            self.post("STFU newfag m(")
        lmsg = "{} {}".format(nick.lower(), lmsg)
        if ("melina" in lmsg or "meiina" in lmsg or "sunna" in lmsg or
                "milena" in lmsg or "milana" in lmsg):
            self.post("Melina is gross!")
        return False
