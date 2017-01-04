import logging
import random

from sqlite3 import OperationalError

from ..commands.command import Command
from ..commands.db import DBCommand
from ..utils import get_json

__all__ = "HolyCommand",

LOGGER = logging.getLogger(__name__)

class HolyCommand(Command, DBCommand):
    def __init__(self, *args, **kw):
        self.verses = self.setup()
        super().__init__(*args, **kw)

    def setup(self):
        cur = self.conn.cursor()
        try:
            try:
                cur.execute("CREATE TABLE quran (verse TEXT)")
                json = get_json(
                    "http://api.globalquran.com/complete/en.sahih?format=json")
                json = [
                    ("{v[surah]}:{v[ayah]}: {v[verse]}".format(v=v),)
                    for v in json["quran"]["en.sahih"].values()]
                LOGGER.info("Importing %d verses", len(json))
                cur.executemany("INSERT INTO quran VALUES(?)", json)
            except OperationalError:
                pass
            cur.execute("SELECT * FROM quran WHERE length(verse) < 300")
            rows = [c[0] for c in cur]
            random.shuffle(rows)
            LOGGER.info("Loaded %d verses", len(rows))
            return rows
        except:
            LOGGER.exception("failed to set up")
            raise

    handlers = "!holy", "!quran"

    def handle_cmd(self, cmd, remainder, msg):
        if not self.allowed(msg):
            return False
        verse = self.verses.pop()
        if not self.verses:
            self.verses = self.setup()
        self.post("{}, the Holy Book says {}", msg.nick, verse)
        return True
