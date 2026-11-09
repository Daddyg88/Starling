"""Voice commands for the settlement map: "show the settlement map tourist one", "hide the settlement map"."""
import re
import time

_HIDE = re.compile(r"\b(?:hide|hidden|close|closed|remove|dismiss|clear|get rid of|turn off|switch off)\b.*\b(?:settlement|settlements)\b.*\b(?:map|maps|layout)\b")
_SHOW = re.compile(r"\b(?:show|open|bring up|display|put up|pull up)\b.*\b(?:settlement|settlements)\b.*\b(?:map|maps|layout)\b")


class SettlementMapVoice:
    def __init__(self, maps, view):
        self.maps = maps
        self.view = view

    def try_handle(self, text):
        said = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said:
            return None
        if _HIDE.search(said):
            self.view.current = None
            return "Settlement map hidden."
        if not _SHOW.search(said):
            return None
        found = self.maps.find(said)
        if found is None:
            names = self.maps.names()
            if not names:
                return "I have no settlement maps yet."
            return "Which settlement map? Say, for example, show settlement map %s." % names[0].lower()
        self.view.current = found["id"]
        self.view.shown_at = time.monotonic()
        return "Showing the %s settlement map." % found.get("name", found["id"])
