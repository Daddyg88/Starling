"""
STREAM EVENTS: a new sub, a resub, gifted subs, a raid, a viewer milestone and chat milestones. Plain Python, no network, no game.

Twitch tells every reader about these (even an anonymous one), YouTube has Super Chats and memberships. Each one becomes a StreamEvent,
which the ChatDirector (streaming/chat.py) turns into one of her lines (voicepacks/default/streaming.json, keys StreamEvent_*).

Safety: a viewer picks their own name, so every name goes through clean_name (letters, digits, underscores, spaces only) and every
number is turned into a small whole number. Nothing in an event is ever treated as a command, and events never touch the game.
"""
import re
from dataclasses import dataclass

MAX_NUMBER = 100000                 # a raid of a million is not something she needs to read out as a million

# the kinds of event, and the line pool each one uses
KINDS = {
    "sub": "StreamEvent_Sub",                  # someone subscribed (or became a member)
    "resub": "StreamEvent_Resub",              # a resub; amount = months
    "gift": "StreamEvent_Gift",                # someone gave subs; amount = how many
    "raid": "StreamEvent_Raid",                # a raid; amount = viewers
    "streak": "StreamEvent_Streak",            # a viewer's watch streak milestone; amount = streams in a row
    "tip": "StreamEvent_Tip",                  # a YouTube Super Chat / Super Sticker (the amount of money is never read out)
    "chat_messages": "StreamEvent_ChatMessages",     # chat passed a round number of messages this stream; amount = messages
    "chat_people": "StreamEvent_ChatPeople",         # a round number of different people have chatted this stream; amount = people
}

# chat milestones: these round numbers, then every CHAT_STEP after the last one
MESSAGE_MILESTONES = (50, 100, 250, 500, 1000)
PEOPLE_MILESTONES = (5, 10, 25, 50, 100)
CHAT_STEP = {"chat_messages": 500, "chat_people": 100}
MAX_PEOPLE_TRACKED = 3000           # the most different names she remembers this session


@dataclass(frozen=True)
class StreamEvent:
    kind: str                 # one of KINDS
    user: str = ""
    amount: int = 0
    platform: str = ""        # "twitch" or "youtube" ("" for chat milestones, which are counted here)


def whole(value, default=0):
    """Any text or number -> a whole number between 0 and MAX_NUMBER (garbage becomes the default)."""
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(0, min(MAX_NUMBER, number))


def clean(name):
    """A name that is safe to say out loud (same rule as chat messages)."""
    name = re.sub(r"[^A-Za-z0-9_ ]", "", str(name or "")).strip()
    return name[:25] or "someone"


def from_twitch(parsed):
    """A parsed Twitch USERNOTICE line (see twitch.parse_line) -> StreamEvent, or None when it is not one she reacts to."""
    if parsed.get("command") != "USERNOTICE":
        return None
    tags = parsed.get("tags") or {}
    what = tags.get("msg-id", "")
    name = clean(tags.get("display-name") or tags.get("login") or parsed.get("user"))
    if what == "sub":
        return StreamEvent("sub", name, 0, "twitch")
    if what == "resub":
        return StreamEvent("resub", name, whole(tags.get("msg-param-cumulative-months"), 2), "twitch")
    if what == "subgift":
        return StreamEvent("gift", name, 1, "twitch")
    if what == "anonsubgift":
        return StreamEvent("gift", "an anonymous viewer", 1, "twitch")
    if what == "submysterygift":
        return StreamEvent("gift", name, max(1, whole(tags.get("msg-param-mass-gift-count"), 1)), "twitch")
    if what == "anonsubmysterygift":
        return StreamEvent("gift", "an anonymous viewer", max(1, whole(tags.get("msg-param-mass-gift-count"), 1)), "twitch")
    if what == "raid":
        return StreamEvent("raid", clean(tags.get("msg-param-displayName") or tags.get("display-name") or tags.get("login")),
                           whole(tags.get("msg-param-viewerCount"), 0), "twitch")
    if what == "viewermilestone" and tags.get("msg-param-category", "watch-streak") == "watch-streak":
        return StreamEvent("streak", name, whole(tags.get("msg-param-value"), 0), "twitch")
    return None


def from_youtube(item):
    """One YouTube liveChat item -> StreamEvent, or None. (Super Chats, Super Stickers, new members, member milestones, gifted memberships.)"""
    snippet = item.get("snippet") or {}
    author = item.get("authorDetails") or {}
    name = clean(author.get("displayName"))
    kind = snippet.get("type")
    if kind in ("superChatEvent", "superStickerEvent"):
        return StreamEvent("tip", name, 0, "youtube")
    if kind == "newSponsorEvent":
        return StreamEvent("sub", name, 0, "youtube")
    if kind == "memberMilestoneChatEvent":
        months = (snippet.get("memberMilestoneChatDetails") or {}).get("memberMonth")
        return StreamEvent("resub", name, whole(months, 2), "youtube")
    if kind == "membershipGiftingEvent":
        count = (snippet.get("membershipGiftingDetails") or {}).get("giftMembershipsCount")
        return StreamEvent("gift", name, max(1, whole(count, 1)), "youtube")
    return None


def next_milestone(kind, count, last):
    """The round number chat has just passed (and not yet been told about), or 0."""
    steps = MESSAGE_MILESTONES if kind == "chat_messages" else PEOPLE_MILESTONES
    every = CHAT_STEP[kind]
    reached = 0
    for step in steps:
        if count >= step:
            reached = step
    if count >= steps[-1]:
        reached = steps[-1] + ((count - steps[-1]) // every) * every
    return reached if reached > last else 0


def pick_pool(event):
    """The line pool for an event. Big gifts and big raids have their own, bigger-sounding pools."""
    base = KINDS[event.kind]
    if event.kind == "gift" and event.amount >= 10:
        return base + "_Big"
    if event.kind == "raid" and event.amount >= 50:
        return base + "_Big"
    if event.kind == "resub" and event.amount >= 12:
        return base + "_Long"
    return base
