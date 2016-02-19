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


__all__ = [
    "XYoutuberCommand",
    "XLiveleakCommand",
    "XIMdbCommand",
    "XRedditCommand",
    "XGithubIssuesCommand",
    "XTwitterCommand",
    ]

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

class XRedditCommand(Command):
    reddit = re.compile(r"https?://(www.)?reddit.com/r/.+?/[\S]+")

    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        for url in self.reddit.finditer(msg.msg):
            url = url.group(0).strip()
            logger.debug("reddit: %s", url)
            try:
                jurl = url + ".json"
                resp = get_json(jurl)
                data = resp[0].get("data").get("children")[0].get("data")
                target = data.get("url")
                score = data.get("score")
                title = data.get("title")
                if not title:
                    raise Exception("Failed to get title")
                is_self = data.get("is_self") or False
                nsfw = data.get("only_18") or False
                if nsfw and not "nfsw" in title.lower():
                    title = "[NSFW] {}".format(title)
                sub = data.get("subreddit", "plebbit")
                if is_self or not target:
                    info = "{title}\n{sub}, Score: {score}".format(title=title, sub=sub, score=score)
                else:
                    info = "{title}\n{sub}, Score: {score}\n{target}".format(title=title, target=target, sub=sub, score=score)
                self.post("Plebbit: {}", info)
            except Exception:
                logger.exception("reddit %s", url)
        return False


class XGithubIssuesCommand(Command):
    issues = re.compile(r"https://github.com/.*?/(?:issues|pull)/\d+")

    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        for url in self.issues.finditer(msg.msg):
            url = url.group(0)
            try:
                resp = get_json(url.strip().replace("https://github.com/", "https://api.github.com/repos/").replace("/pull/", "/pulls/"))
                base = '[{r[state]}] "{r[title]}" by {r[user][login]}'.format(r=resp)
                body = resp.get("body")
                if len(body) > 295 - len(base):
                    body = body[0:295 - len(base)] + "…"
                self.post("{}\n{}", base, body)
            except Exception:
                logger.exception("failed to github")
        return False


class XTwitterCommand(Command):
    twitter = re.compile(r"https://twitter.com/(.*)/status/\d+")
    images = re.compile(r'property="og:image"\s+content="(.*?)"')
    title = re.compile(r'property="og:title"\s+content="(.*?)"')
    desc = re.compile(r'property="og:description"\s+content="(.*?)"')

    def handles(self, cmd):
        return bool(cmd)

    def __call__(self, cmd, remainder, msg):
        for url in self.twitter.finditer(msg.msg):
            user = url.group(1).strip()
            url = url.group(0).strip()
            logger.debug("twitter: %s", url)
            try:
                resp, _ = get_text(url)
                desc = self.desc.search(resp)
                if not desc:
                    continue
                desc = html.unescape(desc.group(1))[1:-1]
                title = self.title.search(resp)
                if not title:
                    continue
                title = html.unescape(title.group(1))
                imgs = [html.unescape(i.group(1)) for i in self.images.finditer(resp) if "profile_images" not in i.group(1)]
                imgs = " ".join(imgs)
                if imgs:
                    info = "{title}:\n{desc}\n{imgs}".format(title=title, desc=desc, imgs=imgs)
                else:
                    info = "{title}:\n{desc}".format(title=title, desc=desc)
                self.post("{}", info)
            except Exception:
                logger.exception("twitter: %s", url)
        return False
