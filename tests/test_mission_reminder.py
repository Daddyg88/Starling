import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from control.mission_reminder import MissionReminder, parse_expiry
from core.event_bus import Event


class Narr:
    def __init__(self): self.said = []
    def say(self, key, fields=None):
        self.said.append((key, fields))
        return True


class Settings:
    def __init__(self, **v): self.v = v
    def get(self, k, d=None): return self.v.get(k, d)


def ev(name, **data):
    return Event(name=name, data=data)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "m.json"
        self.now = [datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)]
        self.clock = [0.0]
        self.narr = Narr()
        self.make()

    def make(self, **settings):
        self.r = MissionReminder(None, Settings(**settings), self.narr, lambda: None, self.path,
                                 now=lambda: self.now[0], clock=lambda: self.clock[0])

    def accept(self, mid=1, expiry="2026-11-01T12:50:00Z", station="Jameson Memorial"):
        self.r.on_event(ev("MissionAccepted", MissionID=mid, LocalisedName="Deliver 20 Gold", Expiry=expiry,
                           DestinationSystem="Shinrarta Dezhra", DestinationStation=station))

    def test_expiry_warned_once_per_threshold(self):
        self.accept()
        self.assertEqual(self.narr.said[0][0], "Missions_Expiring")
        self.assertEqual(self.narr.said[0][1]["Minutes"], 50)
        self.clock[0] += 61
        self.r.on_event(ev("Docked", StationName="Elsewhere"))
        self.assertEqual(len(self.narr.said), 1)                       # already told at the 60 minute mark
        self.now[0] = datetime(2026, 11, 1, 12, 40, tzinfo=timezone.utc)
        self.clock[0] += 61
        self.r.on_event(ev("Docked", StationName="Elsewhere"))
        self.assertEqual(len(self.narr.said), 2)
        self.assertEqual(self.narr.said[1][1]["Minutes"], 10)

    def test_hand_in_on_docking(self):
        self.accept(expiry="2026-11-05T12:00:00Z")
        self.r.on_event(ev("Docked", StationName="jameson memorial"))
        self.assertEqual(self.narr.said[-1][0], "Missions_HandIn")
        self.accept(mid=2, expiry="2026-11-05T12:00:00Z")
        self.r.on_event(ev("Docked", StationName="Jameson Memorial"))
        self.assertEqual((self.narr.said[-1][0], self.narr.said[-1][1]["Count"]), ("Missions_HandInMany", 2))

    def test_finished_missions_are_forgotten(self):
        self.accept(expiry="2026-11-05T12:00:00Z")
        self.r.on_event(ev("MissionCompleted", MissionID=1))
        self.r.on_event(ev("Docked", StationName="Jameson Memorial"))
        self.assertEqual(self.narr.said, [])

    def test_redirect(self):
        self.accept(expiry="2026-11-05T12:00:00Z")
        self.r.on_event(ev("MissionRedirected", MissionID=1, NewDestinationStation="Other Port", NewDestinationSystem="X"))
        self.r.on_event(ev("Docked", StationName="Jameson Memorial"))
        self.assertEqual(self.narr.said, [])
        self.r.on_event(ev("Docked", StationName="Other Port"))
        self.assertEqual(len(self.narr.said), 1)

    def test_expired_missions_are_dropped_and_list_survives_restart(self):
        self.accept(expiry="2026-11-05T12:00:00Z")
        self.make()
        self.assertIn("1", self.r.missions)
        self.now[0] = datetime(2026, 11, 6, tzinfo=timezone.utc)
        self.clock[0] += 61
        self.r.check_expiry()
        self.assertEqual(self.r.missions, {})

    def test_switched_off_and_bad_data(self):
        self.make(**{"missions.reminders": False})
        self.accept()
        self.r.on_event(ev("Docked", StationName="Jameson Memorial"))
        self.assertEqual(self.narr.said, [])
        self.r.on_event(SimpleNamespace(name="MissionAccepted", data=None))
        self.assertIsNone(parse_expiry("garbage"))
        self.path.write_text("nope", encoding="utf-8")
        self.make()
        self.assertEqual(self.r.missions, {})


if __name__ == "__main__":
    unittest.main()
