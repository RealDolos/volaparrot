"""
The MIT License (MIT)
Copyright © 2017 RealDolos

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
import multiprocessing as mp

LOGGER = logging.getLogger(__name__)

def signal_handle(_signal, frame):
    pass

def init_worker():
    try:
        # work around for fucken pool workers being retarded
        import signal
        signal.signal(signal.SIGINT, signal_handle)
    except Exception:
        pass # wangblows might not like it

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)03d %(threadName)s %(levelname)s %(module)s: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("requests").setLevel(logging.WARNING)

    LOGGER.info("starting processor")

def _run_process(*args):
    import subprocess
    try:
        res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode, res.stdout, res.stderr
    except Exception:
        LOGGER.exception("ex running")
        return -1, b"", b""


class Processor:
    def __init__(self):
        self.pool = mp.Pool(5, initializer=init_worker, maxtasksperchild=5)

    def __call__(self, callback, args):
        LOGGER.debug("running %r", args)
        try:
            self.pool.apply_async(
                _run_process,
                args,
                callback=callback,
                error_callback=self.error)
        except Exception:
            LOGGER.exception("failed to run processor")

    def error(*args, **kw):
        LOGGER.error("failed to run processor %r %r", args, kw)
