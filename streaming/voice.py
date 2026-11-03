"""Voice commands for stream chat: "pause the chat", "chat on", "turn off Twitch chat".

Only clear phrases count (a short list, or a sentence that says stream / Twitch / YouTube chat), so ordinary talk
about "chat" never switches viewers on or off by accident."""

import re

_SHORT_OFF = re.compile(r"^(?:(?:please )?(?:pause|mute|stop|ignore) (?:the )?chat|chat (?:off|paused|pause)|(?:turn|switch) (?:the )?chat off|(?:turn|switch) off (?:the )?chat)$")
_SHORT_ON = re.compile(r"^(?:(?:please )?(?:resume|unpause|unmute) (?:the )?chat|chat (?:on|back|resume)|(?:turn|switch) (?:the )?chat on|(?:turn|switch) on (?:the )?chat)$")
_NAMED = r"(?:stream chat|twitch chat|youtube chat|viewer chat|viewers)"
_LONG_OFF = re.compile(r"\b(?:pause|stop|turn off|switch off|disable|mute|ignore)\b.*\b%s\b|\b%s\b.*\b(?:off|pause|paused)\b" % (_NAMED, _NAMED))
_LONG_ON = re.compile(r"\b(?:resume|start|turn on|switch on|enable|unpause|listen to)\b.*\b%s\b|\b%s\b.*\b(?:on|resume|back)\b" % (_NAMED, _NAMED))


class StreamChatVoice:
    def __init__(self, settings, narrator=None):
        self.settings = settings
        self.narrator = narrator

    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said:
            return None
        off = _SHORT_OFF.search(said) or _LONG_OFF.search(said)
        on = None if off else (_SHORT_ON.search(said) or _LONG_ON.search(said))
        if not (off or on):
            return None
        self.settings.set("streaming.enabled", not off)
        try:
            self.settings.save()
        except Exception:
            pass
        if self.narrator is not None:
            self.narrator.say("StreamChat_Paused" if off else "StreamChat_Resumed")
        return "Stream chat paused." if off else "Stream chat is back on."
