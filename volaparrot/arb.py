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
import asyncio
import logging

from time import time
from types import MethodType

import volapi.volapi as volapi_internal

from volapi.arbritrator import call_async, call_sync, ARBITRATOR


__all__ = ["ARBITRATOR"]

LOGGER = logging.getLogger(__name__)


@call_sync
def pulse(self, room, interval=0.2):
    LOGGER.debug("pulse for %s is a go!", repr(room))

    @asyncio.coroutine
    def looper():
        LOGGER.debug("looping %s %s", repr(room), repr(interval))
        while True:
            nextsleep = asyncio.sleep(interval)
            try:
                if room.connected:
                    room.conn.enqueue_data("pulse", time())
                    room.conn.process_queues()
                yield from nextsleep
            except Exception:
                LOGGER.exception("Failed to enqueue pulse")

    asyncio.async(looper(), loop=self.loop)

@call_async
def _call_later(self, room, delay, callback, *args, **kw):
    if not callback:
        return

    def insert():
        if room.connected and room.conn:
            room.conn.enqueue_data("call", [callback, args, kw])
            room.conn.process_queues()

    LOGGER.debug("call later scheduled %r %r %r", room, delay, callback)
    self.loop.call_later(delay, insert)

try:
    volapi_internal.EVENT_TYPES += "pulse", "call",
except AttributeError:
    pass
ARBITRATOR.start_pulse = MethodType(pulse, ARBITRATOR)
ARBITRATOR.call_later = MethodType(_call_later, ARBITRATOR)
