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

from time import time

# pylint: disable=import-error
import isodate

from lru import LRU
# pylint: enable=import-error

from ..utils import get_text, get_json
from .command import Command


__all__ = [
    "XYoutuberCommand",
    "XLiveleakCommand",
    "XIMdbCommand",
    "XRedditCommand",
    "XGithubIssuesCommand",
    "XTwitterCommand",
    ]

logger = logging.getLogger(__name__)

class WebCommand(Command):
    needle = re.compile("^$"), 0
    cooldown = LRU(20)
    timeout = 3 * 60

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        if isinstance(self.needle, str):
            self.needle = self.needle, 0
        if self.needle and isinstance(self.needle[0], str):
            self.needle = re.compile(self.needle[0]), self.needle[1]

    def handles(self, cmd):
        return bool(cmd)

    def fixup(self, url):
        return url

    def __call__(self, cmd, remainder, msg):
        needle, group = self.needle
        now = time()
        for url in needle.finditer(msg.msg):
            url = url.group(group).strip()
            if self.cooldown.get(url, 0) + self.timeout > now:
                continue

            self.cooldown[url] = now
            try:
                url = self.fixup(url)
                if not url:
                    continue
                if self.onurl(url, msg) is False:
                    break
            except Exception:
                logger.exception("failed to process")
        return False

    def onurl(self, url, msg):
        raise NotImplementedError()

    @staticmethod
    def extract(url, *args):
        args = [re.compile(a) if isinstance(a, str) else a for a in args]
        text, _ = get_text(url)
        return [text,] + [a.search(text) for a in args]

    @staticmethod
    def unescape(string):
        if string:
            string = html.unescape(string.strip())
            # shit is double escaped quite often
            string = string.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
            string = re.sub(r"[\s+\n]+", " ", string.replace("\r\n", "\n"))
        return string


class XYoutuberCommand(WebCommand):
    needle = r"https?://(?:www\.)?(?:youtu\.be/\S+|youtube\.com/(?:v|watch|embed)\S+)"

    description = re.compile(r'itemprop="description"\s+content="(.+?)"', re.M | re.S)
    duration = re.compile(r'itemprop="duration"\s+content="(.+?)"', re.M | re.S)
    title = re.compile(r'itemprop="name"\s+content="(.+?)"', re.M | re.S)

    def onurl(self, url, msg):
        _, title, duration, desc = self.extract(url, self.title, self.duration, self.description)
        title = self.unescape(title.group(1))
        if not title:
            return
        if duration:
            duration = str(isodate.parse_duration(duration.group(1)))
        desc = self.unescape(desc.group(1))
        desc = None
        if "mmortal" in msg.nick.lower():
            title += " (probably some shit music only a retard would like)"

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


class XLiveleakCommand(WebCommand):
    needle = r"http://(?:.+?\.)?liveleak\.com/view\?[\S]+"

    description = re.compile(r'property="og:description"\s+content="(.+?)"', re.M | re.S)
    title = re.compile(r'property="og:title"\s+content="(.+?)"', re.M | re.S)

    def onurl(self, url, msg):
        _, title, desc = self.extract(url, self.title, self.description)
        title = self.unescape(title.group(1))
        if not title:
            return
        desc = self.unescape(desc.group(1))

        if desc:
            self.post("{}\n{}", title, desc)
        else:
            self.post("{}", title)


class XIMdbCommand(WebCommand):
    needle = r"imdb\.com/title/(tt\d+)", 1

    def onurl(self, url, msg):
        resp = get_json("http://www.omdbapi.com/?i={}&plot=short&r=json".format(url))
        logger.debug("%s", resp)
        title = resp.get("Title")
        if not resp.get("Response") == "True" or not title:
            return
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


class XRedditCommand(WebCommand):
    needle = r"https?://(www.)?reddit.com/r/.+?/[\S]+"

    def onurl(self, url, msg):
        jurl = url + ".json"
        resp = get_json(jurl)
        data = resp[0].get("data").get("children")[0].get("data")
        target = data.get("url")
        score = data.get("score")
        title = data.get("title")
        if not title:
            return
        is_self = data.get("is_self") or False
        nsfw = data.get("only_18") or False
        if nsfw and not "nfsw" in title.lower():
            title = "[NSFW] {}".format(title)
        sub = data.get("subreddit", "plebbit")

        if is_self or not target:
            info = "{title}\n{sub}, Score: {score}".format(title=title, sub=sub, score=score)
        else:
            info = "{title}\n{sub}, Score: {score}\n{target}".format(
                title=title, target=target, sub=sub, score=score)
        self.post("Plebbit: {}", info)


class XGithubIssuesCommand(WebCommand):
    needle = r"https://github.com/.*?/(?:issues|pull)/\d+"

    def onurl(self, url, msg):
        resp = get_json(
            url.replace("https://github.com/", "https://api.github.com/repos/").
            replace("/pull/", "/pulls/"))
        base = '[{r[state]}] "{r[title]}" by {r[user][login]}'.format(r=resp)
        body = resp.get("body")
        if len(body) > 295 - len(base):
            body = body[0:295 - len(base)] + "…"
        self.post("{}\n{}", base, body)


class XTwitterCommand(WebCommand):
    needle = r"https://twitter.com/(.*)/status/\d+"

    images = re.compile(r'property="og:image"\s+content="(.*?)"', re.M | re.S)
    title = re.compile(r'property="og:title"\s+content="(.*?)"', re.M | re.S)
    desc = re.compile(r'property="og:description"\s+content="(.*?)"', re.M | re.S)

    def onurl(self, url, msg):
        resp, desc, title = self.extract(url, self.desc, self.title)
        desc = self.unescape(desc.group(1))[1:-1]
        if not desc:
            return
        title = self.unescape(title.group(1))
        if not title:
            return
        imgs = [html.unescape(i.group(1))
                for i in self.images.finditer(resp)
                if "profile_images" not in i.group(1)]
        imgs = " ".join(imgs)
        if imgs:
            info = "{title}:\n{desc}\n{imgs}".format(title=title, desc=desc, imgs=imgs)
        else:
            info = "{title}:\n{desc}".format(title=title, desc=desc)
        self.post("{}", info)
