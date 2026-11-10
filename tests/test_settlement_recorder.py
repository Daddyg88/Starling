import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from navigation.settlement_recorder import TRAIL_MAX, SettlementRecorder

# lines in the shape the game really writes (from a real Journal, trimmed)
APPROACH = {"timestamp": "2026-11-09T19:24:00Z", "event": "ApproachSettlement", "Name": "Polischuk Agricultural Biosphere", "MarketID": 3866948352,
            "StationGovernment": "$government_Democracy;", "StationEconomy": "$economy_Agri;", "SystemAddress": 3932277478106, "BodyID": 12,
            "BodyName": "Shinrarta Dezhra A 2", "Latitude": -9.401943, "Longitude": -109.094177}
GRANTED = {"timestamp": "2026-11-09T19:24:43Z", "event": "DockingGranted", "LandingPad": 1, "MarketID": 3866948352,
           "StationName": "Polischuk Agricultural Biosphere", "StationType": "OnFootSettlement"}
DOCKED = {"timestamp": "2026-11-09T19:25:43Z", "event": "Docked", "StationName": "Polischuk Agricultural Biosphere", "StationType": "OnFootSettlement",
          "MarketID": 3866948352, "StationEconomy": "$economy_Agri;", "LandingPads": {"Small": 1, "Medium": 0, "Large": 1}}


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settlement_samples.json"
        self.state = SimpleNamespace(latitude=-9.404991, longitude=-109.09375, heading=0.0, altitude=0.0, planet_radius=4318173.0, status_flags2=0)
        self.clock = Clock()
        self.rec = SettlementRecorder(lambda: self.state, self.path, clock=self.clock, stamp=lambda: "T")

    def saved(self):
        return json.loads(self.path.read_text())

    def test_a_visit_keeps_what_the_game_said(self):
        for entry in (APPROACH, GRANTED, DOCKED):
            self.rec.on_entry(entry)
        visit = self.saved()[0]
        self.assertEqual(visit["settlement"]["Name"], "Polischuk Agricultural Biosphere")
        self.assertEqual(visit["settlement"]["StationEconomy"], "$economy_Agri;")
        self.assertEqual(visit["settlement"]["LandingPads"], {"Small": 1, "Medium": 0, "Large": 1})
        self.assertEqual(visit["settlement"]["PadGiven"], 1)
        self.assertEqual(visit["settlement"]["Latitude"], -9.401943)
        docked = [row for row in visit["journal"] if row["event"] == "Docked"][0]
        self.assertEqual(docked["here"]["lat"], -9.404991)               # where the ship sat when it docked

    def test_nothing_is_recorded_away_from_a_settlement_or_while_replaying(self):
        self.rec.on_entry(DOCKED | {"StationType": "Orbis"})
        self.rec.on_entry(APPROACH, silent=True)
        self.assertEqual(self.rec.visits, [])

    def test_started_after_the_approach_it_begins_from_the_docking(self):
        self.rec.on_entry(DOCKED)
        self.assertEqual(self.saved()[0]["settlement"]["Name"], "Polischuk Agricultural Biosphere")

    def test_the_walking_trail_is_every_two_seconds_and_only_on_foot(self):
        self.rec.on_entry(APPROACH)
        self.rec.on_status(self.state)                                   # in the ship: no trail
        self.state.status_flags2 = 1
        for second in range(0, 11):
            self.clock.now = float(second)
            self.state.heading = float(second * 10)
            self.rec.on_status(self.state)
        trail = self.rec.current["trail"]
        self.assertEqual(len(trail), 6)                                  # seconds 0, 2, 4, 6, 8, 10
        self.assertEqual(trail[1][2], 20.0)

    def test_the_trail_has_a_limit(self):
        self.rec.on_entry(APPROACH)
        self.state.status_flags2 = 1
        for index in range(TRAIL_MAX + 50):
            self.clock.now = index * 3.0
            self.rec.on_status(self.state)
        self.assertEqual(len(self.rec.current["trail"]), TRAIL_MAX)

    def test_marking_a_spot_by_voice(self):
        self.assertIn("not at a settlement", self.rec.try_handle("mark spot power regulator"))
        self.rec.on_entry(APPROACH)
        self.state.status_flags2 = 1
        self.assertEqual(self.rec.try_handle("mark spot power regulator"), "Marked power regulator.")
        self.assertEqual(self.rec.try_handle("record this position"), "Marked spot 2.")
        marks = self.saved()[0]["marks"]
        self.assertEqual([m["label"] for m in marks], ["power regulator", "spot 2"])
        self.assertTrue(marks[0]["on_foot"])
        self.assertAlmostEqual(marks[0]["lat"], -9.404991)
        for said in ("mark", "what is the next jump", "market spot"):
            self.assertIsNone(self.rec.try_handle(said))

    def test_leaving_ends_the_visit_and_the_file_survives_a_restart(self):
        self.rec.on_entry(APPROACH)
        self.rec.on_entry({"event": "SupercruiseEntry"})
        self.assertIsNone(self.rec.current)
        again = SettlementRecorder(lambda: self.state, self.path)
        self.assertEqual(len(again.visits), 1)
        self.assertEqual(again.visits[0]["ended"], "T")

    def test_only_the_last_forty_visits_are_kept(self):
        for _ in range(45):
            self.rec.on_entry(APPROACH)
        self.rec.save()
        self.assertEqual(len(self.saved()), 40)


class WiringTests(unittest.TestCase):
    def test_the_processor_tells_listeners_about_each_line_but_survives_a_broken_one(self):
        from core.event_bus import EventBus
        from journal.processor import EventProcessor
        from events.registry import load_registry
        from journal.game_state import GameState
        seen = []
        processor = EventProcessor(EventBus(), {}, GameState(), load_registry())
        processor.raw_listeners.append(lambda entry, silent: 1 / 0)
        processor.raw_listeners.append(lambda entry, silent: seen.append((entry["event"], silent)))
        processor.handle_entry(dict(APPROACH))
        self.assertEqual(seen, [("ApproachSettlement", False)])


class AfterARestart(RecorderTests):
    def test_the_visit_is_picked_up_again_when_starling_is_started_late(self):
        self.rec.on_entry(APPROACH)
        self.rec.save()
        again = SettlementRecorder(lambda: self.state, self.path, clock=self.clock, stamp=lambda: "T")
        again.on_entry(APPROACH, True)                          # the journal being caught up
        self.assertIs(again.current, again.visits[-1])
        self.assertEqual(len(again.visits), 1)                  # not a second copy of the same visit
        again.on_entry({"event": "SupercruiseEntry"}, True)
        self.assertIsNone(again.current)

    def test_other_events_during_a_visit_are_listed_by_name(self):
        self.rec.on_entry(APPROACH)
        self.rec.on_entry({"timestamp": "T1", "event": "SomethingAtATerminal"})
        self.rec.on_entry({"timestamp": "T2", "event": "Music"})
        names = [row[1] for row in self.rec.current["events"]]
        self.assertEqual(names, ["SomethingAtATerminal"])


if __name__ == "__main__":
    unittest.main()
