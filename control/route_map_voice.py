"""Voice commands for the route map overlay: "hide the route map", "show the route map".

"Galaxy map" is the game's own screen, so this only answers when the sentence says route (or neutron / plotter) AND map / overlay.
"""

import re

_TOPIC = r"(?:route|neutron|plotter|plotted|navigation|nav)"
_THING = r"(?:map|maps|overlay|over lay|display|panel|window|picture)"
_HIDE = re.compile(r"\b(?:hide|hidden|closed|close|closing|remove|dismiss|clear|get rid of|turn off|switch off|disable)\b.*\b%s\b.*\b%s\b" % (_TOPIC, _THING))
_SHOW = re.compile(r"\b(?:show|open|opened|bring up|display|turn on|switch on|enable|put up)\b.*\b%s\b.*\b%s\b" % (_TOPIC, _THING))


class RouteMapVoice:
    def __init__(self, state_provider, narrator=None):
        self.state_provider = state_provider
        self.narrator = narrator

    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said:
            return None
        if "galaxy map" in said or "system map" in said:
            return None                           # those are the game's own screens
        hide = _HIDE.search(said)
        show = _SHOW.search(said)
        if not (hide or show):
            return None
        state = self.state_provider()
        if state is None:
            return None
        state.route_map_hidden = bool(hide)
        if self.narrator is not None:
            self.narrator.say("RouteMap_Hidden" if hide else "RouteMap_Shown")
        return "Route map hidden." if hide else "Route map shown."
