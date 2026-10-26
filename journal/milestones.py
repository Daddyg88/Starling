"""
Round-number milestones from the game's own Statistics event (written when you load in): play-time hours, hyperspace jumps,
first footfalls and biological species. Saved in data/game_milestones.json so a milestone is only ever said once.
The very first time she sees your Statistics she only writes the numbers down (no speech), otherwise a long-time commander
would hear "3,500 hours!" on day one.
"""

from pathlib import Path

from journal.exobiology import _read_json, _write_json

# kind -> (how often, where it is in the Statistics event)
STEPS = {"Hours": 500, "Jumps": 5000, "Footfalls": 100, "Species": 10}


def read_statistics(entry):
    """The numbers we use out of a Statistics journal line (missing ones are left out)."""
    explore = entry.get("Exploration") or {}
    exo = entry.get("Exobiology") or {}
    out = {}
    played = explore.get("Time_Played")
    if isinstance(played, (int, float)):
        out["Hours"] = int(played // 3600)
    for kind, value in (("Jumps", explore.get("Total_Hyperspace_Jumps")), ("Footfalls", explore.get("First_Footfalls")),
                        ("Species", exo.get("Organic_Species_Encountered"))):
        if isinstance(value, (int, float)):
            out[kind] = int(value)
    return out


class GameMilestones:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        data = _read_json(self.path) if self.path else {}
        self.last = {k: v for k, v in (data.get("last") or {}).items() if isinstance(v, (int, float))}
        self.latest = {}                  # the newest Statistics numbers, for her to talk about

    def check(self, entry):
        """Returns [(kind, value)] for every step crossed since last time (the highest round number only, one per kind)."""
        now = read_statistics(entry)
        self.latest = now
        first_time = not self.last
        out = []
        for kind, value in now.items():
            step = STEPS[kind]
            before = self.last.get(kind)
            if before is not None and value // step > before // step and not first_time:
                out.append((kind, value // step * step))
            if before is None or value > before:
                self.last[kind] = value
        self.save()
        return out

    def save(self):
        if self.path:
            _write_json(self.path, {"last": self.last})
