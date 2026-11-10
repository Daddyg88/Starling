"""Voice commands for the settlement map: "show the settlement map tourist one", "hide the settlement map"."""
import re
import time

from navigation.settlement_maps import GROUPS

_HIDE = re.compile(r"\b(?:hide|hidden|close|closed|remove|dismiss|clear|get rid of|turn off|switch off)\b.*\b(?:settlement|settlements)\b.*\b(?:map|maps|layout)\b")
_SHOW = re.compile(r"\b(?:show|open|bring up|display|put up|pull up)\b.*\b(?:settlement|settlements)\b.*\b(?:map|maps|layout)\b")

_NAMED = re.compile(r"\b(?:" + "|".join(re.escape(g) for g in GROUPS) + r")\b")      # she was told a group (tourist, industrial...)


class SettlementMapVoice:
    def __init__(self, maps, view, suggest=None, dismissed=None, options=None):
        self.maps = maps
        self.view = view
        self.dismissed = dismissed or (lambda value: None)      # (True/False): told when you hide or show the map by hand
        self.options = options or (lambda: [])          # () -> the layout names this settlement could be
        self.suggest = suggest or (lambda: None)       # () -> the map id worked out for the settlement you are at

    def try_handle(self, text):
        said = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said:
            return None
        if _HIDE.search(said):
            self.view.current = None
            self.view.target = None
            self.dismissed(True)
            return "Settlement map hidden."
        if not _SHOW.search(said):
            return None
        found = self.maps.find(said)
        if found is None and not _NAMED.search(said):
            found = self.maps.get(self.suggest())             # "show the settlement map" with no name: the one she worked out
        if found is None:
            could = self.options()
            if 1 < len(could) < 8:
                return "I cannot tell which layout this is: %s. Say, for example, show settlement map %s." % (", ".join(could), could[0].lower())
            names = self.maps.names()
            if not names:
                return "I have no settlement maps yet."
            return "Which settlement map? Say, for example, show settlement map %s." % names[0].lower()
        self.view.current = found["id"]
        self.dismissed(False)
        self.view.shown_at = time.monotonic()
        return "Showing the %s settlement map." % found.get("name", found["id"])
