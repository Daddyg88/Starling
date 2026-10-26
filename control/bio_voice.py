"""Voice commands for the exobiology overlay: "hide the bio overlay", "show the biology overlay"."""

import re

_TOPIC = r"(?:bio|by o|biology|biological|exobiology|exo biology|exo|life)"
_THING = r"(?:overlay|over lay|box|panel|list|display|window)"
_HIDE = re.compile(r"\b(?:hide|close|remove|dismiss|clear|get rid of|turn off|switch off|disable)\b.*\b%s\b.*\b%s\b" % (_TOPIC, _THING))
_SHOW = re.compile(r"\b(?:show|open|bring up|display|turn on|switch on|enable|put up)\b.*\b%s\b.*\b%s\b" % (_TOPIC, _THING))


class BioOverlayVoice:
    def __init__(self, state_provider, narrator=None):
        self.state_provider = state_provider
        self.narrator = narrator

    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said:
            return None
        hide = _HIDE.search(said)
        show = _SHOW.search(said)
        if not (hide or show):
            return None
        state = self.state_provider()
        bio = getattr(state, "bio", None)
        if bio is None:
            return None
        bio.hidden = bool(hide)
        if self.narrator is not None:
            self.narrator.say("BioOverlay_Hidden" if hide else "BioOverlay_Shown")
        return "Biology overlay hidden." if hide else "Biology overlay shown."
