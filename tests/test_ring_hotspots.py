import unittest

from events._signals import is_ring, ring_data, ring_hotspots
from personality.line_keys import keys_for
from tests.test_bio_predict import run


def ring(signals, name="Test 3 A Ring", event="SAASignalsFound"):
    return {"event": event, "BodyName": name, "BodyID": 9, "Signals": signals}


PLAT = {"Type": "Platinum", "Type_Localised": "Platinum", "Count": 2}
PAINITE = {"Type": "Painite", "Type_Localised": "Painite", "Count": 1}
MONAZITE = {"Type": "Monazite", "Type_Localised": "Monazite", "Count": 1}


class RingHotspots(unittest.TestCase):
    def test_only_rings_have_hotspots(self):
        self.assertTrue(is_ring("Synuefe AB-C d1 3 A Ring"))
        self.assertFalse(is_ring("Synuefe AB-C d1 3 A"))
        self.assertEqual(ring_hotspots(ring([PLAT], name="Test 3 A")), [])

    def test_counts_and_order(self):
        self.assertEqual(ring_hotspots(ring([PAINITE, PLAT, MONAZITE])), [("Platinum", 2), ("Monazite", 1), ("Painite", 1)])

    def test_planet_signal_types_are_not_minerals(self):
        bio = {"Type": "$SAA_SignalType_Biological;", "Type_Localised": "Biological", "Count": 3}
        self.assertEqual(ring_hotspots(ring([bio])), [])

    def test_the_spoken_summary(self):
        data = ring_data(ring([PLAT, PAINITE, MONAZITE]))
        self.assertEqual((data["Total"], data["Word"]), ("four", "hotspots"))
        self.assertEqual(data["Summary"], "two platinum, one monazite and one painite")
        one = ring_data(ring([PAINITE]))
        self.assertEqual((one["Total"], one["Word"], one["Summary"]), ("one", "hotspot", "one painite"))
        self.assertEqual(ring_data(ring([])), {})

    def test_a_favourite_is_named(self):
        data = ring_data(ring([PAINITE, PLAT]), favourites={"platinum"})
        self.assertEqual(data["Favourite"], "Platinum")
        self.assertEqual(ring_data(ring([PAINITE]), favourites={"platinum"})["Favourite"], "")

    def test_the_event_carries_it_and_says_it_once(self):
        got, _ = run([ring([PLAT, PAINITE]), ring([PLAT, PAINITE])])
        saa = [d for n, d in got if n == "SAASignalsFound"]
        self.assertEqual(saa[0]["Total"], "three")
        self.assertEqual(saa[0]["Summary"], "two platinum and one painite")
        self.assertEqual(len(saa), 1)                      # the game told us twice: she says it once

    def test_fss_rings_work_too(self):
        got, _ = run([ring([MONAZITE], event="FSSBodySignals")])
        fss = [d for n, d in got if n == "FSSBodySignals"]
        self.assertEqual(fss[0]["Summary"], "one monazite")

    def test_lines_exist_and_fill_in(self):
        import json
        from core import paths
        lines = json.loads((paths.ROOT / "voicepacks" / "default" / "rings.json").read_text(encoding="utf-8"))
        data = {"Total": "four", "Word": "hotspots", "Summary": "two platinum and two painite", "Favourite": "Platinum"}
        from types import SimpleNamespace
        self.assertEqual(keys_for(SimpleNamespace(name="SAASignalsFound", data=dict(data)))[0], "RingHotspots_Favourite")
        for key in ("RingHotspots", "RingHotspots_Favourite"):
            for line in lines[key]:
                text = line.format(**data)
                self.assertNotIn("{", text)
        self.assertEqual(keys_for(SimpleNamespace(name="SAASignalsFound", data={"Biological": 2}))[0], "SAASignalsFound_Biological")

    def test_the_voice_pack_loads_the_lines(self):
        from tests.test_dialogue import real_dialogue
        self.assertTrue(real_dialogue().pick("RingHotspots", "", False, False))


if __name__ == "__main__":
    unittest.main()
