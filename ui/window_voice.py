"""Voice commands for her two windows: "show the chat window" / "hide the chat window" and "show the memory window" / "close the memory window".

Only clear phrases count (the word window, list or page is needed), so ordinary talk about chat or memory never opens or closes anything by accident.
The chat window is a setting (Settings > Streaming > Show the chat window), so this just flips it; the memory window ('What she knows about you')
belongs to the dashboard, so the request is handed over (App.request_ui) and the dashboard opens or closes it."""

import re

_OPEN = r"(?:show|open|bring up|display|pop up|put up)(?: me)?"
_SHUT = r"(?:hide|close|dismiss|put away|get rid of|shut|remove)"
_CHAT = r"(?:the |my |our )?(?:stream |twitch |youtube |viewer |viewers )?chat (?:window|box|feed)"
_MEMORY = r"(?:the |my |your )?(?:memory|memories|knowledge|what you know about me|what you know|what you remember)(?: window| list| page)"
_HOLO = r"(?:the |my |your )?(?:hologram|holo|projection)"
_HOLO_ON = re.compile(r"^(?:please )?(?:%s %s|(?:turn|switch) on %s|(?:turn|switch) %s on)$" % (_OPEN, _HOLO, _HOLO, _HOLO))
_HOLO_OFF = re.compile(r"^(?:please )?(?:%s %s|(?:turn|switch) off %s|(?:turn|switch) %s off)$" % (_SHUT, _HOLO, _HOLO, _HOLO))
_CHAT_ON = re.compile(r"^(?:(?:please )?%s %s|(?:please )?(?:turn|switch) (?:on )?%s(?: on)?)$" % (_OPEN, _CHAT, _CHAT))
_CHAT_OFF = re.compile(r"^(?:(?:please )?%s %s|(?:please )?(?:turn|switch) (?:off )?%s(?: off)?)$" % (_SHUT, _CHAT, _CHAT))
_MEMORY_ON = re.compile(r"^(?:please )?%s %s$" % (_OPEN, _MEMORY))
_MEMORY_OFF = re.compile(r"^(?:please )?%s %s$" % (_SHUT, _MEMORY))


def clean(text):
    said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", said).strip()


def which(text):
    """'chat_on', 'chat_off', 'memory_on', 'memory_off' or None."""
    said = clean(text)
    if _HOLO_ON.match(said):
        return "holo_on"
    if _HOLO_OFF.match(said):
        return "holo_off"
    if _CHAT_ON.match(said) and "turn off" not in said and "switch off" not in said:
        return "chat_on"
    if _CHAT_OFF.match(said) or said in ("turn off the chat window", "switch off the chat window", "turn the chat window off", "switch the chat window off"):
        return "chat_off"
    if _MEMORY_ON.match(said):
        return "memory_on"
    if _MEMORY_OFF.match(said):
        return "memory_off"
    return None


class WindowVoice:
    def __init__(self, settings, request_ui, narrator=None):
        self.settings = settings
        self.request_ui = request_ui
        self.narrator = narrator

    def _say(self, key, text):
        if self.narrator is not None:
            self.narrator.say(key)
        return text

    def try_handle(self, text):
        what = which(text)
        if what is None:
            return None
        if what in ("holo_on", "holo_off"):
            on = what == "holo_on"
            self.settings.set("hologram.enabled", on)
            try:
                self.settings.save()
            except Exception:
                pass
            if on:
                self.request_ui("hologram_test")           # show her for a few seconds so you can see it worked, even with the game closed
            return self._say("Window_HologramShown" if on else "Window_HologramHidden", "Hologram on." if on else "Hologram off.")
        if what in ("chat_on", "chat_off"):
            on = what == "chat_on"
            self.settings.set("streaming.window", on)
            try:
                self.settings.save()
            except Exception:
                pass
            if on and not self.settings.get("streaming.enabled", False):
                return self._say("Window_ChatNeedsChat", "The chat window will show once chat is switched on. Say 'chat on'.")
            return self._say("Window_ChatShown" if on else "Window_ChatHidden", "Chat window shown." if on else "Chat window hidden.")
        self.request_ui("memory_window" if what == "memory_on" else "memory_window_close")
        return self._say("Window_MemoryShown" if what == "memory_on" else "Window_MemoryHidden",
                         "Here is what I know about you." if what == "memory_on" else "Closed.")
