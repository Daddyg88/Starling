"""
Reads Twitch chat. Read only: it joins as an anonymous viewer ("justinfan..."), which Twitch allows, so no password, no token
and no Twitch login are needed. It cannot post in chat (that comes later, with a bot login).

parse_line() and channel_name() are plain Python (tested). TwitchChat is the little network loop; it reconnects by itself.
"""

import random
import re
import socket
import ssl
import threading
import time

from core.logger import get_logger
from streaming.chat import ChatMessage
from streaming.events import from_twitch

log = get_logger("twitch")

HOST, PORT = "irc.chat.twitch.tv", 6697
READ_TIMEOUT = 420          # Twitch pings about every 5 minutes; silence for longer than this means the line is dead
RETRY_SECONDS = (3, 6, 12, 30, 60)
_CHANNEL = re.compile(r"^[A-Za-z0-9_]{3,25}$")


def channel_name(text):
    """'Daddyg88', '#daddyg88', 'https://www.twitch.tv/Daddyg88' -> 'daddyg88'. '' when it is not a channel name."""
    text = str(text or "").strip()
    found = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", text)
    if found:
        text = found.group(1)
    text = text.lstrip("#@").strip()
    return text.lower() if _CHANNEL.match(text) else ""


def parse_line(line):
    """One IRC line -> {"command", "tags", "user", "channel", "text"} (missing parts are empty)."""
    line = line.rstrip("\r\n")
    tags = {}
    if line.startswith("@"):
        raw, _, line = line[1:].partition(" ")
        for pair in raw.split(";"):
            key, _, value = pair.partition("=")
            tags[key] = value
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    head, _, trailing = line.partition(" :")
    parts = head.split()
    command = parts[0] if parts else ""
    channel = parts[1].lstrip("#") if len(parts) > 1 and parts[1].startswith("#") else ""
    return {"command": command, "tags": tags, "user": prefix.split("!")[0], "channel": channel, "text": trailing}


def message_from(parsed, owner_channel=""):
    """A PRIVMSG line -> ChatMessage (who is a moderator or subscriber comes from Twitch's own badges)."""
    tags = parsed["tags"]
    badges = {b.split("/")[0] for b in str(tags.get("badges", "")).split(",") if b}
    owner = "broadcaster" in badges or (owner_channel and parsed["user"].lower() == owner_channel.lower())
    mod = owner or tags.get("mod") == "1" or "moderator" in badges
    sub = tags.get("subscriber") == "1" or bool(badges & {"subscriber", "founder"})
    name = tags.get("display-name") or parsed["user"]
    return ChatMessage("twitch", name, parsed["text"], mod=bool(mod), sub=bool(sub), owner=bool(owner))


def open_socket():
    raw = socket.create_connection((HOST, PORT), timeout=15)
    wrapped = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
    wrapped.settimeout(READ_TIMEOUT)
    return wrapped


class TwitchChat:
    def __init__(self, channel, on_message, on_status, connect=open_socket, sleep=time.sleep):
        self.channel = channel_name(channel)
        self.on_message = on_message
        self.on_status = on_status
        self._connect = connect
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread = None
        self._sock = None

    def start(self):
        if self._thread is not None or not self.channel:
            return
        self._thread = threading.Thread(target=self._run, name="twitch-chat", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _run(self):
        attempt = 0
        while not self._stop.is_set():
            self.on_status("Connecting to #%s..." % self.channel)
            try:
                self._session()
                attempt = 0 if self._joined else attempt + 1
            except (OSError, ssl.SSLError) as error:
                if self._stop.is_set():
                    return
                log.info("Twitch chat connection problem: %s", error)
                attempt += 1
                self.on_status("Can't reach Twitch right now (%s)" % (str(error) or type(error).__name__))
            except Exception:
                log.exception("Twitch chat failed")
                attempt += 1
                self.on_status("Twitch chat hit a problem. See the log.")
            if self._stop.is_set():
                return
            wait = RETRY_SECONDS[min(attempt, len(RETRY_SECONDS)) - 1] if attempt else RETRY_SECONDS[0]
            self.on_status("Reconnecting in %d seconds..." % wait)
            self._sleep(wait)

    def _session(self):
        self._joined = False
        sock = self._sock = self._connect()
        try:
            for line in ("CAP REQ :twitch.tv/tags twitch.tv/commands", "PASS SCHMOOPIIE",
                         "NICK justinfan%d" % random.randint(10000, 99999), "JOIN #%s" % self.channel):
                sock.sendall((line + "\r\n").encode("utf-8"))
            buffer = b""
            while not self._stop.is_set():
                data = sock.recv(4096)
                if not data:
                    raise OSError("Twitch closed the connection")
                buffer += data
                while b"\r\n" in buffer:
                    raw, buffer = buffer.split(b"\r\n", 1)
                    if self._handle(raw.decode("utf-8", "replace"), sock):
                        return                              # Twitch asked us to reconnect
                if len(buffer) > 65536:
                    buffer = b""                            # never grow without limit
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _handle(self, line, sock):
        parsed = parse_line(line)
        command = parsed["command"]
        if command == "PING":
            sock.sendall(("PONG :%s\r\n" % (parsed["text"] or "tmi.twitch.tv")).encode("utf-8"))
        elif command == "RECONNECT":
            return True
        elif command == "JOIN" and not self._joined:
            self._joined = True
            self.on_status("Connected to #%s" % self.channel)
        elif command == "NOTICE" and "authentication failed" in parsed["text"].lower():
            self.on_status("Twitch refused the connection: %s" % parsed["text"])
        elif command == "PRIVMSG":
            self.on_message(message_from(parsed, self.channel))
        elif command == "USERNOTICE":
            event = from_twitch(parsed)               # a sub, resub, gift, raid or watch streak: the bridge gives it to the director
            if event is not None:
                self.on_message(event)
        return False
