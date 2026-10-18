"""
Plays mp3 files using Windows' built-in media system (MCI).
No extra software needs to be installed, and it uses almost no memory.
"""

import sys
import threading
import time

from core.logger import get_logger

log = get_logger("mci")


class PlaybackError(Exception):
    pass


def _make_winmm_send():
    """Connect to Windows' winmm.dll. Returns send(command) -> (error_code, text)."""
    import ctypes
    winmm = ctypes.windll.winmm

    def send(command):
        buffer = ctypes.create_unicode_buffer(256)
        error = winmm.mciSendStringW(command, buffer, 255, 0)
        if error:
            message = ctypes.create_unicode_buffer(256)
            winmm.mciGetErrorStringW(error, message, 255)
            return error, message.value
        return 0, buffer.value

    return send


class MciPlayer:
    def __init__(self, send=None, max_seconds=60):
        self._send = send
        self._custom_send = send is not None
        self.max_seconds = max_seconds
        self._stop = threading.Event()
        self._counter = 0

    def available(self):
        return self._custom_send or sys.platform == "win32"

    def _sender(self):
        if self._send is None:
            self._send = _make_winmm_send()
        return self._send

    def stop(self):
        self._stop.set()

    def play(self, path, volume=100):
        """Play one mp3 and wait until it ends (or stop() is called)."""
        send = self._sender()
        self._stop.clear()
        self._counter += 1
        alias = "starling%d" % self._counter

        error, message = send('open "%s" type mpegvideo alias %s' % (path, alias))
        if error:
            raise PlaybackError("could not open %s: %s" % (path, message))
        try:
            send("setaudio %s volume to %d" % (alias, max(0, min(100, int(volume))) * 10))
            error, message = send("play %s" % alias)
            if error:
                raise PlaybackError("could not play %s: %s" % (path, message))
            deadline = time.monotonic() + self.max_seconds
            time.sleep(0.05)
            while not self._stop.is_set() and time.monotonic() < deadline:
                error, mode = send("status %s mode" % alias)
                if error or mode != "playing":
                    break
                time.sleep(0.05)
        finally:
            send("stop %s" % alias)
            send("close %s" % alias)
