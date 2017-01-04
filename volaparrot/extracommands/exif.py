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

from io import BytesIO

import exifread

from ..utils import requests, get_json
from ..commands.command import FileCommand


__all__ = ["ExifCommand"]

LOGGER = logging.getLogger(__name__)


def gps(src):

    class LatStub:
        values = "N"


    class LonStub:
        values = "E"


    def deg(values):
        hour, minute, sec = [float(v.num) / float(v.den) for v in values]
        return hour + (minute / 60.0) + (sec / 3600.0)


    if not hasattr(src, "read"):
        src = BytesIO(src)
    exif = exifread.process_file(src, details=False)
    lat = deg(exif["GPS GPSLatitude"].values)
    if exif.get("GPS GPSLatitudeRef", LatStub()).values != "N":
        lat = 0 - lat
    lon = deg(exif["GPS GPSLongitude"].values)
    if exif.get("GPS GPSLongitudeRef", LonStub()).values != "E":
        lon = 0 - lon
    return (lat, lon,
            "{} {}".format(exif.get("Image Make", "Unknown"),
                           exif.get("Image Model", "Unknown")))


class ExifCommand(FileCommand):

    def onfile(self, file):
        if not self.active:
            return False

        url = file.url
        urll = url.lower()
        if (not urll.endswith(".jpeg") and not urll.endswith(".jpe") and
                not urll.endswith(".jpg") and not urll.endswith(".png")):
            return False
        if file.size > 10 * 1024 * 1024:
            LOGGER.info("Ignoring %s because too large", file)
            return False
        ttldiff = self.room.config["ttl"] - file.time_left
        if ttldiff > 10:
            LOGGER.info("Ignoring %s because too old", file)
            return False

        LOGGER.info("%s %s %d %d %d", file, url, file.size, file.time_left, ttldiff)
        lat, lon, model = gps(requests.get(url).content)
        maps = "https://www.google.com/maps?f=q&q=loc:{:.7},{:.7}&t=k&spn=0.5,0.5".format(lat, lon)
        loc = get_json(
            "http://maps.googleapis.com/maps/api/geocode/json?"
            "latlng={:.7},{:.7}&sensor=true&language=en".format(lat, lon))
        loc = {v.get("types")[0]: v.get("formatted_address") for v in loc["results"]}
        useloc = None
        for i in ("street_address", "route", "postal_code",
                  "administrative_area_level_3", "administrative_area_level_2",
                  "locality", "administrative_level_1", "country"):
            useloc = loc.get(i)
            if useloc:
                break
        if not useloc:
            useloc = "Unknown place"
        self.post("@{} {}\nGPS: {}\nModel: {}", file.id, useloc, maps, model)
