"""
MANNERS - saying "thank you" to Starling.

After you ask her for something by voice, saying "thank you" (in the same sentence, or just after) makes her say
"you're welcome" (a different wording each time) and gives her mood a small lift. Not saying it costs nothing:
there is no penalty, ever. Each request can only be thanked once, and the mood engine's usual soft cap and hourly
cap stop anyone farming points by saying it over and over.
"""
import re

from core.event_bus import Event
from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("manners")

THANKS = re.compile(r"\b(thank you|thank-you|thankyou|thank u|thanks|many thanks|cheers|much appreciated|i appreciate (it|that))\b")
FILLER = re.compile(r"\b(very much|so much|a lot|a million|starling|commander|cmdr|love|darling|mate|please|ok|okay|"
                    r"and|that was|that's|great|lovely|brilliant|perfect|for that|for the help|for your help|then|again)\b")
THANK_WINDOW_SECONDS = 30.0


def has_thanks(text):
    return bool(THANKS.search((text or "").lower()))


def only_thanks(text):
    """True for a sentence that is nothing but a thank-you ("thank you", "thanks Starling", "thank you very much")."""
    lowered = (text or "").lower()
    if not THANKS.search(lowered):
        return False
    rest = FILLER.sub(" ", THANKS.sub(" ", lowered))
    return not re.sub(r"[^a-z0-9]+", "", rest)


class Manners:
    def __init__(self, bus, speech, dialogue, settings, mood=None, clock=None):
        import time
        self.bus, self.speech, self.dialogue, self.settings, self.mood = bus, speech, dialogue, settings, mood
        self.clock = clock or time.monotonic
        self.last_request = None          # when your last request was heard
        self.thanked = True               # has that request been thanked already?

    def attach(self):
        self.bus.subscribe("voice.heard", self.on_heard)

    def detach(self):
        self.bus.unsubscribe("voice.heard", self.on_heard)

    def _addressed(self, data):
        if data.get("wake") or (data.get("ptt") and self.settings.get("ptt.skip_wake", True)):
            return True
        return not self.settings.get("stt.require_wake", True)

    def on_heard(self, event):
        try:
            self._heard(event.data or {})
        except Exception:
            log.exception("Manners problem")                 # manners must never break the voice commands

    def _heard(self, data):
        if not self._addressed(data):
            return
        text = data.get("command") if data.get("wake") else data.get("text")
        if not (text or "").strip():
            return
        now = self.clock()
        if has_thanks(text):
            alone = only_thanks(text)
            if not alone:                                     # "plot the route, thank you": a request AND thanks
                self.last_request, self.thanked = now, False
            recent = self.last_request is not None and now - self.last_request <= THANK_WINDOW_SECONDS
            if recent and not self.thanked:
                self.thanked = True
                self._reward()
            self._welcome()
        else:
            self.last_request, self.thanked = now, False

    def _reward(self):
        if self.mood is not None:
            self.mood.on_event(Event(name="Thanked", data={}, priority="normal"))

    def _welcome(self):
        if self.speech is None or self.dialogue is None or not self.settings.get("speech.enabled", True):
            return
        line = self.dialogue.pick("YoureWelcome", effective_mood(self.settings),
                                  bool(self.settings.get("speech.allow_mature", False)), False)
        if line is not None:
            self.speech.say(text=personalise(line.text, self.settings), priority="normal", event_name="manners.welcome")
