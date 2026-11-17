"""
The chat feed: every Twitch and YouTube chat message (and every sub, raid and gift) in the order it arrived, kept for the chat window.
Plain Python, no network, no screen, so it is tested. The reader threads add lines; the window asks for what is new since the last
look (by number), so nothing is ever read twice and a slow window never makes the chat readers wait.

Names and text are cleaned the same way as everything else from chat (no emoji, no control characters, a sensible length).
"""
import threading
import time
from collections import deque
from dataclasses import dataclass

from streaming.chat import clean_name, tidy

MAX_LINES = 300            # the feed keeps this many; older lines drop off
MAX_TEXT = 300             # a longer message is cut here


@dataclass(frozen=True)
class FeedLine:
    seq: int               # 1, 2, 3 ... in arrival order
    kind: str              # "chat" or "event"
    platform: str          # "twitch" or "youtube" ("" for something else)
    user: str = ""
    text: str = ""
    mod: bool = False
    sub: bool = False
    owner: bool = False
    when: float = 0.0      # wall-clock time (for a HH:MM stamp)


def describe_event(event):
    """A StreamEvent -> one plain line, e.g. 'Ann subscribed', 'Bob gifted 5 subs', 'Raid from Cy: 30 viewers'. '' if it is not worth a line."""
    who, amount = event.user or "someone", int(event.amount or 0)
    kind = event.kind
    if kind == "sub":
        return "%s subscribed" % who
    if kind == "resub":
        return "%s resubscribed%s" % (who, " (%d months)" % amount if amount else "")
    if kind == "gift":
        return "%s gifted %d sub%s" % (who, max(1, amount), "" if amount <= 1 else "s")
    if kind == "raid":
        return "Raid from %s%s" % (who, ": %d viewers" % amount if amount else "")
    if kind == "streak":
        return "%s is on a %d stream watch streak" % (who, amount) if amount else ""
    if kind == "tip":
        return "%s sent a Super Chat" % who
    return ""                 # chat milestones are counted by the director, not shown here


class ChatFeed:
    def __init__(self, clock=time.time, max_lines=MAX_LINES):
        self._lines = deque(maxlen=max_lines)
        self._seq = 0
        self._lock = threading.Lock()
        self._clock = clock

    def _add(self, **fields):
        with self._lock:
            self._seq += 1
            line = FeedLine(self._seq, when=self._clock(), **fields)
            self._lines.append(line)
            return line

    def add_message(self, message):
        """A chat.ChatMessage. Empty messages are ignored."""
        text = tidy(getattr(message, "text", ""))[:MAX_TEXT]
        if not text:
            return None
        return self._add(kind="chat", platform=str(getattr(message, "platform", "") or ""), user=clean_name(message.user), text=text,
                         mod=bool(getattr(message, "mod", False)), sub=bool(getattr(message, "sub", False)),
                         owner=bool(getattr(message, "owner", False)))

    def add_event(self, event):
        """A streaming.events.StreamEvent (sub, raid, gift...)."""
        text = describe_event(event)
        if not text:
            return None
        return self._add(kind="event", platform=str(getattr(event, "platform", "") or ""), user=event.user or "", text=tidy(text)[:MAX_TEXT])

    def since(self, seq=0):
        """Every line newer than `seq`, oldest first (what the window has not drawn yet)."""
        with self._lock:
            return [line for line in self._lines if line.seq > seq]

    def last_seq(self):
        with self._lock:
            return self._seq

    def clear(self):
        with self._lock:
            self._lines.clear()
