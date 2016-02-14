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
import html
import re

# pylint: disable=import-error
import isodate
# pylint: enable=import-error

from ..utils import get_text, get_json
from .command import Command


__all__ = ["XYoutuberCommand", "XLiveleakCommand", "XIMdbCommand"]

logger = logging.getLogger(__name__)


class XYoutuberCommand(Command):
    description = re.compile(r'itemprop="description"\s+content="(.+?)"')
    duration = re.compile(r'itemprop="duration"\s+content="(.+?)"')
    title = re.compile(r'itemprop="name"\s+content="(.+?)"')
    youtube = re.compile(
        r"https?://(?:www\.)?(?:youtu\.be/\S+|youtube\.com/(?:v|watch|embed)\S+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.youtube.finditer(msg.msg):
            try:
                resp, _ = get_text(url.group(0).strip())
                title = self.title.search(resp)
                if not title:
                    continue
                title = html.unescape(title.group(1).strip())
                if not title:
                    continue
                duration = self.duration.search(resp)
                if duration:
                    duration = str(isodate.parse_duration(duration.group(1)))
                desc = self.description.search(resp)
                desc = None
                if desc:
                    desc = html.unescape(desc.group(1)).strip()
                if "liquid" in msg.nick.lower():
                    self.post("{}: YouNow links are not allowed, you pedo", msg.nick)
                elif duration and desc and msg.nick.lower() not in ("dongmaster", "doc"):
                    self.post("YouTube: {} ({})\n{}", title, duration, desc)
                elif duration:
                    self.post("YouTube: {} ({})", title, duration)
                elif desc:
                    self.post("YouTube: {}\n{}", title, desc)
                else:
                    self.post("YouTube: {}", title)
            except Exception:
                logger.exception("youtubed")
        return False


class XLiveleakCommand(Command):
    description = re.compile(r'property="og:description"\s+content="(.+?)"')
    title = re.compile(r'property="og:title"\s+content="(.+?)"')
    liveleak = re.compile(r"http://(?:.+?\.)?liveleak\.com/view\?[\S]+")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.liveleak.finditer(msg.msg):
            try:
                resp, _ = get_text(url.group(0).strip())
                title = self.title.search(resp)
                if not title:
                    continue
                title = html.unescape(title.group(1).strip())
                if not title:
                    continue
                desc = self.description.search(resp)
                if desc:
                    desc = html.unescape(desc.group(1)).strip()
                if desc:
                    self.post("{}\n{}", title, desc)
                else:
                    self.post("{}", title)
            except Exception:
                logger.exception("liveleaked")
        return False


class XIMdbCommand(Command):
    imdb = re.compile(r"imdb\.com/title/(tt\d+)")

    def handles(self, cmd):
        return True

    def __call__(self, cmd, remainder, msg):
        for url in self.imdb.finditer(msg.msg):
            try:
                resp = get_json(
                    "http://www.omdbapi.com/?i={}&plot=short&r=json".format(url.group(1).strip()))
                logger.debug("%s", resp)
                title = resp.get("Title")
                if not resp.get("Response") == "True" or not title:
                    continue
                sid = resp.get("seriesID")
                if sid:
                    sid = get_json("http://www.omdbapi.com/?i={}&plot=short&r=json".format(sid))
                    try:
                        title = "{} S{:02}E{:02} - {}".format(sid.get("Title"),
                                                              int(resp.get("Season", "0")),
                                                              int(resp.get("Episode", "0")),
                                                              title)
                    except Exception:
                        logger.exception("series")
                year = resp.get("Year", "0 BC")
                rating = resp.get("imdbRating", "0.0")
                rated = resp.get("Rated", "?")
                runtime = resp.get("Runtime", "over 9000 mins")
                plot = resp.get("Plot")
                if not plot:
                    self.post("{}\n{}, {}, {}, {}", title, year, rating, rated, runtime)
                else:
                    self.post("{}\n{}, {}, {}, {}\n{}", title, year, rating, rated, runtime, plot)
            except Exception:
                logger.exception("imdbed")
        return False


