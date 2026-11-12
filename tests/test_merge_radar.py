import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import merge_radar as mr            # noqa: E402

R = 1699980.5
PER = math.pi / 180 * R
LAT0, LON0 = 55.401119, 53.797638


def blob():
    spots = json.loads((ROOT / "tests" / "fixtures" / "makubuya_radar_spots.json").read_text())
    points = [{"kind": "terminal", "lat": LAT0 + s["n"] / PER, "lon": LON0 + s["e"] / (PER * math.cos(math.radians(LAT0))), "n": s["seen"]} for s in spots]
    return {"settlements": {"4358173443": {"name": "Makubuya Engineering Silo", "layout": None, "pictures": 23, "radius": R,
                                           "origin": [LAT0, LON0], "points": points}}}


class MergeRadarTests(unittest.TestCase):
    def test_two_testers_sightings_of_the_same_terminal_become_one(self):
        one = mr.merge([("a.zip", blob())])["4358173443"]
        two = mr.merge([("a.zip", blob()), ("b.zip", blob())])["4358173443"]
        self.assertEqual(len(one["points"]), len(two["points"]))
        self.assertEqual(two["pictures"], 46)
        self.assertEqual(mr.survey({"4358173443": two})["4358173443"]["testers"], 2)

    def test_corrections_only_move_terminals_with_two_sightings_and_a_good_fit(self):
        merged = mr.merge([("a.zip", blob()), ("b.zip", blob())])["4358173443"]
        data = json.loads((ROOT / "maps" / "settlements" / "industrial_2.json").read_text())
        fit, changes = mr.corrections(merged, data)
        self.assertGreaterEqual(fit[2], mr.MIN_FITTED)
        self.assertTrue(changes)
        for _index, old, new, n in changes:
            self.assertGreaterEqual(n, mr.MIN_SIGHTINGS)
            self.assertLess(math.hypot(old[0] - new[0], old[1] - new[1]) * 0.325, 12)      # a few metres, never a jump across the base

    def test_a_bad_fit_changes_nothing(self):
        merged = mr.merge([("a.zip", blob())])["4358173443"]
        merged["points"] = merged["points"][:2]
        data = json.loads((ROOT / "maps" / "settlements" / "industrial_2.json").read_text())
        self.assertEqual(mr.corrections(merged, data)[1], [])


if __name__ == "__main__":
    unittest.main()
