import io
import math
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from navigation import hack as hack_module
from navigation import radar_read
from navigation.hack import HackMode, blip_wav, modem_wav, progress_of
from navigation.radar_points import PointStore
from navigation.settlement_maps import SettlementMaps

FIX = Path(__file__).parent / "fixtures" / "radar"
RADIUS = 1_699_980.5
PER = math.pi / 180 * RADIUS


class Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class Narrator:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append(key)
        return True


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def radar_screen():
    """A 1920 x 1080 'screen' with a real radar picture (two terminals, two recharge points) in the radar corner."""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    radar = np.asarray(Image.open(FIX / "radar_05.png").convert("RGB"))
    left, top, right, bottom = radar_read.crop_box(1920, 1080)
    screen[top:bottom, left:right] = radar
    return screen


class Rig:
    def __init__(self, **settings):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PointStore(Path(self.tmp.name) / "points.json", stamp=lambda: "t")
        self.narrator = Narrator()
        self.clock = Clock()
        self.state = SimpleNamespace(status_flags2=33041, latitude=55.4, longitude=53.8, heading=0.0, planet_radius=RADIUS)
        self.settlement = {"name": "Makubuya Engineering Silo", "market": 4358173443, "group": "Industrial", "pads": None, "map": None}
        self.sounds = []
        self.screen = radar_screen()
        self.maps = SettlementMaps()
        self.hack = HackMode(Settings(**settings), lambda: self.state, lambda: self.settlement, self.store, self.maps, self.narrator,
                             capture=lambda: self.screen, sound=self.sounds.append, clock=self.clock, spawn=lambda f: None)

    def walk(self, metres_north):
        self.state.latitude += metres_north / PER

    def cleanup(self):
        self.tmp.cleanup()


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)

    def test_only_hack_phrases_are_taken(self):
        h = self.rig.hack
        for said in ("what time is it", "hack", "show settlement map", "radar test", "hello there"):
            self.assertIsNone(h.try_handle(said), said)

    def test_start_phrases(self):
        for said in ("Start hack.", "hack the base", "Hack the base!", "start the hack", "begin scan", "hack this settlement", "map the base"):
            rig = Rig()
            self.addCleanup(rig.cleanup)
            self.assertIn("Hack started", rig.hack.try_handle(said), said)
            self.assertTrue(rig.hack.active)

    def test_not_at_a_base(self):
        self.rig.settlement = None
        self.rig.hack.try_handle("start hack")
        self.assertEqual(self.rig.narrator.said, ["Hack_NoSettlement"])
        self.assertFalse(self.rig.hack.active)

    def test_not_on_foot(self):
        self.rig.state.status_flags2 = 0
        self.rig.hack.try_handle("start hack")
        self.assertEqual(self.rig.narrator.said, ["Hack_NotOnFoot"])

    def test_switched_off_in_the_settings(self):
        rig = Rig(**{"hack.enabled": False})
        self.addCleanup(rig.cleanup)
        rig.hack.try_handle("start hack")
        self.assertEqual(rig.narrator.said, ["Hack_Disabled"])
        self.assertFalse(rig.hack.active)

    def test_start_plays_the_modem_and_says_the_start_line(self):
        self.rig.hack.try_handle("start hack")
        self.assertEqual(self.rig.narrator.said, ["Hack_Start"])
        self.assertEqual(len(self.rig.sounds), 1)

    def test_sound_off_is_silent(self):
        rig = Rig(**{"hack.sound": "Off"})
        self.addCleanup(rig.cleanup)
        rig.hack.try_handle("start hack")
        self.assertEqual(rig.sounds, [])

    def test_stop(self):
        self.rig.hack.try_handle("start hack")
        self.assertEqual(self.rig.hack.try_handle("stop the hack"), "Hack cancelled.")
        self.assertFalse(self.rig.hack.active)
        self.assertEqual(self.rig.hack.result["how"], "aborted")
        self.assertEqual(self.rig.hack.try_handle("stop hack"), "There is no hack running.")

    def test_a_second_start_is_refused(self):
        self.rig.hack.try_handle("start hack")
        self.rig.hack.try_handle("start hack")
        self.assertEqual(self.rig.narrator.said.count("Hack_AlreadyRunning"), 1)

    def test_this_base_is_a_layout_is_noted(self):
        out = self.rig.hack.try_handle("this base is industrial two")
        self.assertIn("Industrial 2", out)
        self.assertEqual(self.rig.store.get("4358173443")["layout"], "industrial_2")


class RunningTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)
        self.hack = self.rig.hack

    def test_a_tick_keeps_the_radar_points(self):
        self.hack.start()
        self.assertTrue(self.hack.tick())
        counts = self.rig.store.counts("4358173443")
        self.assertEqual(counts["terminal"], 2)
        self.assertEqual(counts["recharge"], 2)
        self.assertEqual(self.rig.store.get("4358173443")["pictures"], 1)

    def test_standing_still_does_not_add_the_same_points_again(self):
        self.hack.start()
        for _ in range(4):
            self.hack.tick()
        self.assertEqual(self.rig.store.counts("4358173443")["terminal"], 2)
        self.assertEqual(self.rig.store.points("4358173443", "terminal")[0]["n"], 4)

    def test_progress_grows_as_she_walks_and_milestones_are_spoken_once(self):
        self.hack.start()
        before = self.hack.progress
        for _ in range(8):
            self.rig.walk(15)
            self.hack.tick()
        self.assertGreater(self.hack.progress, before)
        said = self.rig.narrator.said
        self.assertEqual(len(said), len(set(said)))                   # no line twice

    def test_it_finishes_when_there_is_enough_and_tells_the_layout(self):
        self.rig.settlement["map"] = "industrial_2"
        store = self.rig.store
        store.describe("4358173443", name="x")
        e = store.entry("4358173443")
        e["origin"] = [55.4, 53.8]
        e["radius"] = RADIUS
        e["cells"] = [[i, 0] for i in range(40)]
        e["points"] = ([{"kind": "terminal", "lat": 55.4 + i * 1e-4, "lon": 53.8, "n": 3} for i in range(9)]
                       + [{"kind": "ammo", "lat": 55.41, "lon": 53.8, "n": 1}] * 4)
        self.hack.start()
        done = []
        self.hack.on_complete.append(done.append)
        handed = []
        self.hack.on_layout.append(lambda layout, market: handed.append((layout, market)))
        self.hack.on_layout.append(lambda layout, market: 1 / 0)            # one failing hand-over never stops the rest
        for _ in range(hack_module.MIN_PICTURES + 1):
            if not self.hack.tick():
                break
        self.assertFalse(self.hack.active)
        self.assertEqual(self.hack.result["how"], "complete")
        self.assertEqual(self.hack.result["layout"], "industrial_2")
        self.assertIn("Hack_Complete", self.rig.narrator.said)
        self.assertIn("Hack_Layout", self.rig.narrator.said)
        self.assertTrue(store.get("4358173443")["done"])
        self.assertEqual(len(done), 1)
        self.assertEqual(handed, [("industrial_2", "4358173443")])

    def test_it_cannot_finish_before_the_minimum_pictures(self):
        e = self.rig.store.entry("4358173443")
        e["cells"] = [[i, 0] for i in range(40)]
        self.hack.start()
        self.hack.tick()
        self.assertTrue(self.hack.active)

    def test_it_ends_after_the_time_limit(self):
        self.hack.start()
        self.rig.clock.now += 11 * 60
        self.assertFalse(self.hack.tick())
        self.assertEqual(self.hack.result["how"], "timeout")
        self.assertIn("Hack_Timeout", self.rig.narrator.said)

    def test_leaving_the_base_ends_it(self):
        self.hack.start()
        self.rig.settlement = None
        self.assertFalse(self.hack.tick())
        self.assertEqual(self.hack.result["how"], "lost")

    def test_back_on_the_ship_pauses_it(self):
        self.hack.start()
        self.rig.state.status_flags2 = 0
        self.assertTrue(self.hack.tick())
        self.assertIn("PAUSED", self.hack.status)
        self.assertEqual(self.rig.store.get("4358173443")["pictures"], 0)

    def test_no_radar_gives_up_and_says_so(self):
        self.rig.screen = None
        self.hack.capture = lambda: None
        self.hack.start()
        for _ in range(hack_module.FAILS_BEFORE_GIVING_UP):
            self.hack.tick()
        self.assertFalse(self.hack.active)
        self.assertIn("Hack_NoRadar", self.rig.narrator.said)

    def test_a_crash_in_a_follow_up_does_not_stop_the_others(self):
        self.hack.start()
        calls = []
        self.hack.on_complete.append(lambda r: 1 / 0)
        self.hack.on_complete.append(calls.append)
        self.rig.clock.now += 11 * 60
        self.hack.tick()
        self.assertEqual(len(calls), 1)


class MappedTests(unittest.TestCase):
    def test_arrival_says_once_and_only_when_not_mapped(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        h = rig.hack
        approach = {"event": "ApproachSettlement", "Name": "Makubuya Engineering Silo", "MarketID": 4358173443}
        h.on_entry(approach)
        h.on_entry(approach)
        self.assertEqual(rig.narrator.said, ["Hack_Offer"])
        h.on_entry(dict(approach, MarketID=5), silent=True)
        self.assertEqual(len(rig.narrator.said), 1)

    def test_an_anarchy_base_is_called_out_as_a_good_place(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "Den", "MarketID": 11, "StationGovernment": "$government_Anarchy;"})
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "Calm", "MarketID": 12, "StationGovernment": "$government_Democracy;"})
        self.assertEqual(rig.narrator.said, ["Hack_Pirate", "Hack_Offer"])

    def test_a_mapped_anarchy_base_is_not_called_out(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        rig.hack.survey = {"11": {"terminals": 9, "pictures": 40}}
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "Den", "MarketID": 11, "StationGovernment": "$government_Anarchy;"})
        self.assertEqual(rig.narrator.said, ["Hack_Known"])

    def test_known_from_the_testers_survey(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        rig.hack.survey = {"7": {"terminals": 9, "pictures": 40}}
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "x", "MarketID": 7})
        self.assertEqual(rig.narrator.said, ["Hack_Known"])

    def test_a_thin_survey_does_not_count(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        rig.hack.survey = {"7": {"terminals": 2, "pictures": 4}}
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "x", "MarketID": 7})
        self.assertEqual(rig.narrator.said, ["Hack_Offer"])

    def test_done_by_you_is_silent(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        rig.store.mark_done("7")
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "x", "MarketID": 7})
        self.assertEqual(rig.narrator.said, [])

    def test_the_announcement_can_be_switched_off(self):
        rig = Rig(**{"hack.announce": False})
        self.addCleanup(rig.cleanup)
        rig.hack.on_entry({"event": "ApproachSettlement", "Name": "x", "MarketID": 7})
        self.assertEqual(rig.narrator.said, [])


class PartsTests(unittest.TestCase):
    def test_progress_numbers(self):
        none, items = progress_of({}, 0, 0, 7)
        self.assertEqual(none, 0.0)
        full, items = progress_of({"terminal": 7, "ammo": 2, "recharge": 1, "turret": 1}, 7, 30, 7)
        self.assertAlmostEqual(full, 1.0)
        self.assertEqual([i[0] for i in items], ["Terminals", "Gun posts and supplies", "Ground covered"])
        half, _ = progress_of({"terminal": 7}, 0, 0, 7)
        self.assertAlmostEqual(half, 0.45)

    def test_the_numbers_never_pass_their_targets(self):
        _, items = progress_of({"terminal": 20, "ammo": 20}, 20, 99, 7)
        self.assertTrue(all(found <= needed for _l, found, needed in items))

    def test_the_modem_sound_is_a_real_wav_of_about_six_seconds(self):
        with wave.open(io.BytesIO(modem_wav())) as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 6.0, delta=0.1)

    def test_the_blip_is_a_short_wav(self):
        with wave.open(io.BytesIO(blip_wav())) as w:
            self.assertLess(w.getnframes() / w.getframerate(), 0.5)

    def test_snapshot(self):
        rig = Rig()
        self.addCleanup(rig.cleanup)
        h = rig.hack
        self.assertIsNone(h.snapshot())
        h.start()
        self.assertTrue(h.snapshot()["active"])
        h.stop()
        snap = h.snapshot()
        self.assertTrue(snap["done"])
        rig.clock.now += 60
        self.assertIsNone(h.snapshot())


if __name__ == "__main__":
    unittest.main()
