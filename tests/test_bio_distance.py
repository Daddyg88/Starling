"""The 'far enough from the last sample' beep."""

import json
import unittest
from pathlib import Path

from core.event_bus import Event, EventBus
from journal.bio_distance import BioDistance, surface_distance
from journal.game_state import GameState
from tests.test_phase6b import make_settings

RADIUS = 3_000_000.0                  # a 3000 km planet
METRE = 360.0 / (2 * 3.141592653589793 * RADIUS)        # degrees of latitude per metre


class Narr:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, fields))
        return True


class Distance(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(surface_distance(0, 0, 0, 0, RADIUS), 0)
        self.assertAlmostEqual(surface_distance(0, 0, 100 * METRE, 0, RADIUS), 100, delta=0.5)
        self.assertAlmostEqual(surface_distance(10, 20, 10, 20 + 1, 1000), surface_distance(10, 21, 10, 20, 1000))


class Alert(unittest.TestCase):
    def build(self, **values):
        from core import paths
        from journal.exobiology import ExobiologyTracker
        self.state, self.narr, self.beeps = GameState(), Narr(), []
        self.state.exobiology = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        self.bus = EventBus()
        self.d = BioDistance(self.bus, self.narr, make_settings(**values), lambda: self.state,
                             beep=lambda: self.beeps.append(1), spawn=lambda fn: fn())
        self.move(0)

    def move(self, metres):
        self.state.latitude, self.state.longitude, self.state.planet_radius = metres * METRE, 10.0, RADIUS

    def scan(self, genus="Bacterium", complete=False):
        self.d.on_scan(Event("ScanOrganic", {"Genus_Localised": genus, "Species_Localised": genus + " Informem",
                                              "Complete": complete}))

    def test_beeps_and_speaks_once_when_far_enough(self):
        self.build()
        self.scan("Bacterium")                       # 500 m
        self.move(300)
        self.assertFalse(self.d.check(self.state))
        self.move(520)
        self.assertTrue(self.d.check(self.state))
        self.assertEqual(self.beeps, [1])
        self.assertEqual(self.narr.said[0][0], "BioFarEnough")
        self.assertEqual(self.narr.said[0][1]["distance"], "500")
        self.move(900)
        self.assertFalse(self.d.check(self.state))   # only once per sample
        self.assertEqual(len(self.narr.said), 1)

    def test_distance_depends_on_the_genus(self):
        self.build()
        self.scan("Aleoida")                         # 150 m
        self.move(160)
        self.assertTrue(self.d.check(self.state))

    def test_second_sample_starts_again(self):
        self.build()
        self.scan("Aleoida")
        self.move(200)
        self.d.check(self.state)
        self.scan("Aleoida")                         # sample 2 taken here
        self.move(250)
        self.assertFalse(self.d.check(self.state))
        self.move(400)
        self.assertTrue(self.d.check(self.state))

    def test_finished_species_cancels(self):
        self.build()
        self.scan("Aleoida")
        self.scan("Aleoida", complete=True)
        self.move(1000)
        self.assertFalse(self.d.check(self.state))

    def test_no_position_no_alert(self):
        self.build()
        self.state.latitude = None
        self.scan("Aleoida")
        self.assertIsNone(self.d.anchor)
        self.move(1000)
        self.assertFalse(self.d.check(self.state))

    def test_switches(self):
        self.build(exobiology__distance_alert=False)
        self.scan("Aleoida")
        self.move(500)
        self.assertFalse(self.d.check(self.state))
        self.build(exobiology__distance_beep=False)
        self.scan("Aleoida")
        self.move(500)
        self.assertTrue(self.d.check(self.state))
        self.assertEqual(self.beeps, [])
        self.assertEqual(len(self.narr.said), 1)

    def test_lines(self):
        data = json.loads(Path("voicepacks/default/biodistance.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertFalse([b for b in banned if b in line.lower()], line)


class StatusFeedsPosition(unittest.TestCase):
    def test_status_reader_stores_position_and_calls_listeners(self):
        from journal.status_reader import StatusReader
        from tests.test_callouts import make_processor
        processor, _bus, _heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        seen = []
        reader.listeners.append(lambda state: seen.append((state.latitude, state.longitude, state.planet_radius)))
        reader.handle_status({"Flags": 1 << 24, "Latitude": 12.5, "Longitude": -40.0, "PlanetRadius": 2.5e6})
        self.assertEqual(seen[-1], (12.5, -40.0, 2.5e6))
        reader.handle_status({"Flags": 1 << 24})
        self.assertEqual(seen[-1], (None, None, None))

    def test_a_broken_listener_does_not_stop_the_reader(self):
        from journal.status_reader import StatusReader
        from tests.test_callouts import make_processor
        processor, _bus, _heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.listeners.append(lambda state: 1 / 0)
        reader.handle_status({"Flags": 1 << 24})
        self.assertTrue(processor.state.status_seen)
