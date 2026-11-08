"""
Reads YouTube live chat. Read only, and it needs two things from you: a free YouTube Data API key (made once in Google Cloud)
and the link of the live stream. It cannot post in chat.

Polling costs "quota" (Google gives a free 10,000 units a day; one check costs 5). So she checks every 10 seconds at the fastest,
which is enough for about 5 and a half hours of streaming per key per day.

video_id(), parse_messages() and the small helpers are plain Python (tested). YouTubeChat is the polling loop; it never crashes the app.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core.logger import get_logger
from streaming.chat import ChatMessage

log = get_logger("youtube")

API = "https://www.googleapis.com/youtube/v3/"
MIN_POLL, MAX_POLL = 10.0, 60.0
NO_CHAT_RETRY = 30.0
QUOTA_RETRY = 600.0
KEY_RETRY = 60.0
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id(text):
    """A YouTube watch/live/share link, or just the 11 letter video id -> the id. '' when it is neither."""
    text = str(text or "").strip()
    if _ID.match(text):
        return text
    found = re.search(r"(?:v=|youtu\.be/|/live/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", text)
    return found.group(1) if found else ""


def looks_like_key(text):
    """Google API keys are about 39 characters of letters, digits, - and _ (usually starting AIza)."""
    return bool(re.match(r"^[A-Za-z0-9_-]{30,60}$", str(text or "").strip()))


def poll_seconds(milliseconds):
    """Google says how long to wait; we never go faster than MIN_POLL (quota) or slower than MAX_POLL."""
    try:
        wanted = float(milliseconds) / 1000.0
    except (TypeError, ValueError):
        wanted = MIN_POLL
    return max(MIN_POLL, min(MAX_POLL, wanted))


def parse_messages(page):
    """A liveChat/messages answer -> list of ChatMessage (ordinary text messages only: no super chats, joins or bans)."""
    found = []
    for item in (page or {}).get("items") or []:
        snippet = item.get("snippet") or {}
        author = item.get("authorDetails") or {}
        if snippet.get("type") != "textMessageEvent":
            continue
        text = (snippet.get("textMessageDetails") or {}).get("messageText") or snippet.get("displayMessage") or ""
        owner = bool(author.get("isChatOwner"))
        mod = owner or bool(author.get("isChatModerator"))
        sub = bool(author.get("isChatSponsor"))
        found.append(ChatMessage("youtube", author.get("displayName") or "someone", text, mod=mod, sub=sub, owner=owner))
    return found


def error_reason(body):
    """The 'reason' word out of a Google error answer ('quotaExceeded', 'keyInvalid'...), or ''."""
    try:
        data = json.loads(body)
        return str(((data.get("error") or {}).get("errors") or [{}])[0].get("reason") or "")
    except (ValueError, TypeError, AttributeError, IndexError):
        return ""


class ApiError(Exception):
    def __init__(self, status, reason=""):
        super().__init__("YouTube answered %s %s" % (status, reason))
        self.status, self.reason = status, reason


def http_get(url, timeout=15):
    """GET a URL and return the parsed JSON. Raises ApiError for an HTTP error (without ever putting the key in the message)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Starling"}), timeout=timeout) as reply:
            return json.loads(reply.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise ApiError(error.code, error_reason(body)) from None
    except urllib.error.URLError as error:
        raise OSError(str(getattr(error, "reason", "") or "no connection")) from None


class YouTubeChat:
    def __init__(self, key, video, on_message, on_status, get=http_get, sleep=None):
        self.key = str(key or "").strip()
        self.video = video_id(video)
        self.on_message = on_message
        self.on_status = on_status
        self._get = get
        self._stop = threading.Event()
        self._sleep = sleep or (lambda seconds: self._stop.wait(seconds))
        self._thread = None
        self.chat_id = ""
        self.page_token = ""

    def start(self):
        if self._thread is not None or not self.key or not self.video:
            return
        self._thread = threading.Thread(target=self._run, name="youtube-chat", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ---- the loop ----
    def _url(self, what, **params):
        params["key"] = self.key
        return API + what + "?" + urllib.parse.urlencode(params)

    def _run(self):
        wait = 0.0
        while not self._stop.is_set():
            if wait:
                self._sleep(wait)
                if self._stop.is_set():
                    return
            try:
                wait = self.step()
            except ApiError as error:
                wait = self._api_problem(error)
            except OSError as error:
                log.info("YouTube chat connection problem: %s", error)
                self.on_status("Can't reach YouTube right now (%s)" % (str(error) or "no connection"))
                wait = 15.0
            except Exception:
                log.exception("YouTube chat failed")
                self.on_status("YouTube chat hit a problem. See the log.")
                wait = 30.0

    def step(self):
        """One round: find the chat if we do not have it yet, otherwise fetch new messages. Returns seconds to wait."""
        if not self.chat_id:
            return self._find_chat()
        return self._fetch()

    def _find_chat(self):
        self.on_status("Looking for the live chat...")
        page = self._get(self._url("videos", part="liveStreamingDetails", id=self.video))
        items = page.get("items") or []
        if not items:
            self.on_status("YouTube can't find that video. Check the link.")
            return NO_CHAT_RETRY
        chat_id = (items[0].get("liveStreamingDetails") or {}).get("activeLiveChatId") or ""
        if not chat_id:
            self.on_status("That video has no live chat right now. Waiting for the stream to go live...")
            return NO_CHAT_RETRY
        self.chat_id, self.page_token = chat_id, ""
        self._first = True
        self.on_status("Connected to the YouTube live chat")
        return 0.0

    def _fetch(self):
        params = {"liveChatId": self.chat_id, "part": "snippet,authorDetails", "maxResults": 200}
        if self.page_token:
            params["pageToken"] = self.page_token
        page = self._get(self._url("liveChat/messages", **params))
        self.page_token = page.get("nextPageToken") or self.page_token
        messages = parse_messages(page)
        if getattr(self, "_first", False):
            self._first = False                       # the chat already had a backlog: never act on old messages
        else:
            for message in messages:
                self.on_message(message)
        self._refused = 0
        self.on_status("Connected to the YouTube live chat")
        return poll_seconds(page.get("pollingIntervalMillis"))

    def _api_problem(self, error):
        reason = error.reason
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            self.on_status("YouTube's daily limit for your key is used up. It resets at midnight Pacific time.")
            return QUOTA_RETRY
        if reason in ("keyInvalid", "API_KEY_INVALID", "accessNotConfigured", "ipRefererBlocked") or error.status in (400, 401):
            self.on_status("YouTube refused the key. Check it, and that the YouTube Data API v3 is switched on for it.")
            return KEY_RETRY
        if reason in ("liveChatEnded", "liveChatNotFound", "liveChatDisabled") or error.status == 404:
            self.chat_id = ""
            self.on_status("That live chat has ended or is not available. Waiting...")
            return NO_CHAT_RETRY
        # Anything else (a plain 403 'forbidden' for example): wait longer each time (30 s, 1, 2, then 5 minutes) so a key that is simply
        # not allowed does not hammer YouTube all stream (the 0.88.0 log had 405 tries in 3.5 hours). Only the first few are logged.
        self._refused = getattr(self, "_refused", 0) + 1
        wait = min(300.0, 30.0 * (2 ** (self._refused - 1)))
        if self._refused <= 3:
            log.info("YouTube chat answered %s %s", error.status, reason)
        if error.status == 403:
            self.on_status("YouTube said no (403 %s). The key may be restricted (Google Cloud > Credentials > API restrictions), or this chat is not open to it. Trying again in %d s." % (reason or "forbidden", wait))
        else:
            self.on_status("YouTube said no (%s %s). Retrying..." % (error.status, reason))
        return wait
