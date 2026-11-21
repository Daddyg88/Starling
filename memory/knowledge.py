"""
WHAT SHE KNOWS ABOUT YOU: everything she has kept about you, as one plain list the dashboard window can show, each line with a Forget button.
Plain Python (no screen), so it is tested. It only reads what the other parts already keep and asks them to forget ONE thing; it never adds anything.

Groups, in the order shown:
    You told me      likes, dislikes, pets, favourites          (data/player_profile.json)
    People           people you told her about                  (data/people.json)
    Moments          records, deaths, big missions, firsts      (the memory database)
    Habits           stations you keep returning to, systems where you keep dying   (data/habits.json)
    Sessions         a one-line record of each play session     (data/stats.json)
    Totals           hours together, jumps, missions...         (these only go with "Forget everything")
Anything that is missing or fails is skipped: the window must open even when part of her memory is off.
"""
from dataclasses import dataclass

from core.logger import get_logger

log = get_logger("knowledge")

GROUPS = ("You told me", "People", "Moments", "Habits", "Sessions", "Totals")


@dataclass(frozen=True)
class Entry:
    group: str
    text: str
    source: str = ""          # which part keeps it: profile, people, memory, station, deaths, session ("" = cannot be forgotten one by one)
    kind: str = ""
    key: str = ""

    @property
    def can_forget(self):
        return bool(self.source)


def _minutes(minutes):
    minutes = int(minutes or 0)
    if minutes >= 90:
        return "about %d hours" % round(minutes / 60.0)
    return "%d minutes" % minutes if minutes else ""


def session_text(row):
    """'9 Nov: 18 jumps, 3 kills, 2 deaths, about 2 hours, ended in Colonia, 42 people in chat'."""
    parts = []
    for name, one, many in (("jumps", "jump", "jumps"), ("kills", "kill", "kills"), ("deaths", "death", "deaths"), ("docks", "docking", "dockings")):
        n = int(row.get(name, 0) or 0)
        if n:
            parts.append("%d %s" % (n, one if n == 1 else many))
    length = _minutes(row.get("minutes"))
    if length:
        parts.append(length)
    if row.get("system"):
        parts.append("ended in %s" % row["system"])
    if int(row.get("people", 0) or 0) >= 1:
        parts.append("%d people in chat" % row["people"])
    return "%s: %s" % (row.get("ended") or "?", ", ".join(parts) or "a short session")


class Knowledge:
    def __init__(self, store=None, profile=None, people=None, habits=None, stats=None):
        self.store, self.profile, self.people, self.habits, self.stats = store, profile, people, habits, stats

    # ---- reading ----
    def entries(self):
        out = []
        for part in (self._told, self._people, self._moments, self._habits, self._sessions, self._totals):
            try:
                out += part()
            except Exception:
                log.exception("Could not list part of what she knows")
        return out

    def _told(self):
        p = self.profile
        if p is None:
            return []
        rows = [Entry("You told me", "You like %s" % x, "profile", "like", x) for x in p.likes]
        rows += [Entry("You told me", "You dislike %s" % x, "profile", "dislike", x) for x in p.dislikes]
        rows += [Entry("You told me", ("You have a %s called %s" % (x["kind"], x["name"].capitalize())) if x["name"] else "You have a %s (no name yet)" % x["kind"],
                       "profile", "pet", x["name"]) for x in p.pets]
        rows += [Entry("You told me", "Your favourite %s is %s" % (cat, thing), "profile", "fav", cat) for cat, thing in p.favourites.items()]
        return rows

    def _people(self):
        if self.people is None:
            return []
        rows = []
        for name in list(self.people.items):
            info = self.people.describe(name)
            text = "%s, your %s" % (info["name"], info["relation"]) + (" (%s)" % info["place"] if info["place"] else "")
            rows.append(Entry("People", text, "people", "", name))
        return rows

    def _moments(self):
        if self.store is None:
            return []
        return [Entry("Moments", m["summary"][:140], "memory", "", str(m["id"])) for m in self.store.all(60)]

    def _habits(self):
        if self.habits is None:
            return []
        rows = [Entry("Habits", "You often dock at %s (%d times)" % (name, count), "station", "", name)
                for name, count in self.habits.top_stations(5) if count >= 3]
        rows += [Entry("Habits", "You have been destroyed in %s %d times" % (name, count), "deaths", "", name)
                 for name, count in self.habits.death_places() if count >= 2]
        return rows

    def _sessions(self):
        if self.stats is None:
            return []
        return [Entry("Sessions", session_text(row), "session", "", row["id"]) for row in self.stats.sessions() if row.get("id")]

    def _totals(self):
        if self.store is None:
            return []
        s = self.store.stats()
        hours = float(s.get("hours_together", 0) or 0)
        if not (hours or s.get("systems_visited") or s.get("missions_completed") or s.get("times_destroyed")):
            return []
        return [Entry("Totals", "Time together: %.1f hours. Jumps: %s. Missions: %s. Times destroyed: %s. (These only go with 'Forget everything'.)" % (
            hours, s.get("systems_visited", 0), s.get("missions_completed", 0), s.get("times_destroyed", 0)))]

    def grouped(self):
        """[(group name, [entries])] in the order shown, leaving out empty groups."""
        entries = self.entries()
        return [(g, [e for e in entries if e.group == g]) for g in GROUPS if any(e.group == g for e in entries)]

    # ---- forgetting ONE thing ----
    def forget(self, entry):
        """Asks the part that keeps it to forget it. True if something was forgotten."""
        try:
            if entry.source == "profile" and self.profile is not None:
                return self.profile.remove(entry.kind, entry.key)
            if entry.source == "people" and self.people is not None:
                return self.people.remove(entry.key)
            if entry.source == "memory" and self.store is not None:
                self.store.forget(int(entry.key))
                return True
            if entry.source == "station" and self.habits is not None:
                return self.habits.forget_station(entry.key)
            if entry.source == "deaths" and self.habits is not None:
                return self.habits.forget_death_place(entry.key)
            if entry.source == "session" and self.stats is not None:
                return self.stats.forget_session(entry.key)
        except Exception:
            log.exception("Could not forget %r", entry)
        return False
