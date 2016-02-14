#!/usr/bin/env python3
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

import json
import sys


__all__ = ["roomstat"]


def _roomstat(room):
    from volapi import Room
    with Room(room, "letest") as remote:
        remote.listen(onusercount=lambda x: False)
        return (remote.title, max(remote.user_count, 0),
                len(remote.files), remote.config.get("disabled"))

def roomstat(room):
    import subprocess
    cmd = (sys.executable, __file__, room)
    result = subprocess.check_output(cmd, timeout=3).decode()
    result = json.loads(result)
    if isinstance(result, dict) and "message" in result:
        raise IOError("Failed to stat room: {} {}".format(result["type"], result["message"]))
    return result

if __name__ == "__main__":
    try:
        print(json.dumps(_roomstat(sys.argv[1])))
    except Exception as ex:
        print(json.dumps(dict(type=str(type(ex)), message=str(ex))))
