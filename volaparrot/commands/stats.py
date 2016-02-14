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
import os

from collections import defaultdict
from functools import partial
from statistics import mean, median, stdev

from .command import Command


__all__ = ["RoomStatsCommand"]

logger = logging.getLogger(__name__)


def to_size(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 900.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0

    return "%.1f%s%s" % (num, 'Yi', suffix)


class Stat:
    def __init__(self):
        self.sizes = list()

    def add(self, size):
        self.sizes += size,

    @property
    def rawsize(self):
        return sum(self.sizes)

    @property
    def size(self):
        return to_size(sum(self.sizes))

    @property
    def num(self):
        return len(self.sizes)

    @property
    def min(self):
        return to_size(min(self.sizes))

    @property
    def max(self):
        return to_size(max(self.sizes))

    @property
    def mean(self):
        return to_size(mean(self.sizes))

    @property
    def median(self):
        return to_size(median(self.sizes))

    @property
    def stdev(self):
        return to_size(stdev(self.sizes) if len(self.sizes) > 1 else 0.0)


class RoomStatsCommand(Command):
    handlers = ".roomstats", ".stats", ".typestats", ".extstats"
    types = {"user": lambda user, file: user == file.uploader.casefold(),
             "type": lambda type, file: type == file.type.casefold(),
             "ext": lambda ext, file:
                 os.path.splitext(file.name)[1].casefold() in (ext, "." + ext),
             "name": lambda name, file: name in file.name.casefold()}

    def _gen_filters(self, remainder):
        filters = list()
        for word in remainder.split(" "):
            typ = list(i.strip().casefold() for i in word.split(":", 1))
            if len(typ) == 2:
                typ, word = typ
            else:
                typ, word = "name", typ[0]
            filters += partial(self.types[typ]
                               if typ in self.types
                               else self.types["name"],
                               word),
        return filters

    @staticmethod
    def _count(files):
        counts = defaultdict(Stat)
        types = defaultdict(Stat)
        exts = defaultdict(Stat)
        total = Stat()
        for file in files:
            counts[file.uploader].add(file.size)
            types[file.type.casefold()].add(file.size)
            ext = os.path.splitext(file.name)[1] or "Unknown"
            exts[ext.casefold()].add(file.size)
            total.add(file.size)
        return counts, types, exts, total

    def __call__(self, cmd, remainder, msg):
        if cmd.lower() == ".stats":
            user = list(i.strip() for i in remainder.split(" ", 1))
            user, remainder = user if len(user) == 2 else (user[0], "")
            if not user:
                user = msg.nick
            remainder = "user:{} {}".format(user, remainder)

        filters = self._gen_filters(remainder)
        files = list(f for f in self.room.files
                     if all(fi(f) for fi in filters))
        logger.info("Filtered %d files", len(files))

        counts, types, exts, total = self._count(files)

        if cmd.lower() == ".stats":
            counts = counts.get(user, Stat())
            if not counts.num:
                self.post("{} is a faggot and didn't upload anything.\n"
                          "May he be raped by many blackkoks!", user)
                return True
            self.post("{}: {} files totaling {}\n"
                      "Min: {} / Max: {} / Mean: {} / "
                      "Median: {} / StDev: {}",
                      self.nonotify(user), counts.num, counts.size,
                      counts.min, counts.max, counts.mean,
                      counts.median, counts.stdev)
            return True

        if not total.num:
            if not filters:
                self.post("This room is fucking empty and the people in "
                          "this room are henceforth fucking retards!")
            else:
                self.post("Didn't find anything, soooory")
            return True

        if cmd.lower() == ".typestats":
            counts = types
        elif cmd.lower() == ".extstats":
            counts = exts

        counts = sorted(counts.items(),
                        key=lambda i: (-i[1].rawsize, i[0])
                        )[:10]
        counts = list("#{})\u00a0{}: {} [{}]".
                      format(i + 1, self.nonotify(u), e.size, e.num)
                      for i, (u, e) in enumerate(counts))
        trunc = list()
        total = "{} files totaling {}".format(total.num, total.size)
        rem = 300 - len(total) - 25
        for count in counts:
            if len(count) > rem:
                break
            rem -= len(count)
            trunc += count,
        self.post("{}\n{}",
                  total, ", ".join(trunc))
        return True
