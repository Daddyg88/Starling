"""The extra wordings in voicepacks/default/fresh.json (added after reading a tester's logs) and tools/repeat_report.py."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from personality.dialogue import DialogueManager  # noqa: E402
import repeat_report  # noqa: E402

FRESH = ROOT / "voicepacks" / "default" / "fresh.json"
# the pools a tester heard dozens of times; each must now be at least this big (lines in all its files together)
MIN_POOL = {"LaunchVessel": 12, "BoardedShip": 10, "Shutdown": 10, "InDanger": 10, "VeryHotWarning": 8, "VeryColdWarning": 8,
            "HardpointsRetracted": 10, "HardpointsDeployed": 12, "NavRoute": 24, "SystemMapClosed": 14, "GalaxyMapClosed": 14,
            "Touchdown": 28, "Liftoff": 28, "FsdCharging": 36, "BioFarEnough": 20, "VehicleChanged_OnFoot": 24}


class FreshLinesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(FRESH.read_text(encoding="utf-8"))
        cls.manager = DialogueManager(pack_dir=ROOT / "voicepacks" / "default").load()

    def lines(self):
        return {k: v for k, v in self.data.items() if not k.startswith("_")}

    def test_file_is_valid_plain_text_lines(self):
        self.assertGreater(len(self.lines()), 30)
        for key, lines in self.lines().items():
            self.assertIsInstance(lines, list, key)
            for line in lines:
                self.assertIsInstance(line, str, key)
                self.assertTrue(line.strip(), key)
                self.assertNotIn("||", line, key)                      # the two-part marker is for hand-written pairs only

    def test_no_line_twice_in_a_key_or_already_in_the_pool(self):
        for key, lines in self.lines().items():
            lowered = [l.lower().strip() for l in lines]
            self.assertEqual(len(lowered), len(set(lowered)), "repeated inside " + key)
            old = [l.text.lower().strip() for l in self.manager.lines[key]]
            for l in lowered:
                self.assertEqual(old.count(l), 1, "'%s' is in %s more than once (also in an older file)" % (l, key))

    def test_only_known_placeholders(self):
        for key, lines in self.lines().items():
            for line in lines:
                for word in re.findall(r"\{(\w+)\}", line):
                    self.assertEqual((key, word), ("BioFarEnough", "distance"))

    def test_every_key_extends_an_existing_pool(self):
        for key, lines in self.lines().items():
            self.assertGreater(len(self.manager.lines[key]), len(lines), key + " has no older lines: is the key name right?")

    def test_the_pools_a_tester_wore_out_are_bigger_now(self):
        for key, minimum in MIN_POOL.items():
            total = sum(len(v) for k, v in self.manager.lines.items() if k == key or k.startswith(key + "_"))
            self.assertGreaterEqual(total, minimum, key)

    def test_a_small_pool_is_not_heard_twice_in_a_row_any_more(self):
        manager = DialogueManager(pack_dir=ROOT / "voicepacks" / "default").load()
        heard = [manager.pick("LaunchVessel").text for _ in range(14)]
        self.assertEqual(len(set(heard)), 14)                          # a pool of 15 uses a line only once before most others


class RepeatReportTests(unittest.TestCase):
    def test_reads_said_lines_and_ranks_small_pools_first(self):
        log = "\n".join(
            ["2026-01-01 10:00:0%d,000 | INFO     | starling.speech | Said [LaunchVessel]: Vessel away." % (i % 10) for i in range(10)]
            + ["2026-01-01 10:01:00,000 | INFO     | starling.speech | Said [Touchdown]: Touchdown. || later"]
            + ["not a speech line"])
        rows = repeat_report.said_lines(log)
        self.assertEqual(len(rows), 11)
        lines_by_key = {"LaunchVessel": ["Vessel away.", "Launch successful."], "Touchdown": ["Touchdown.", "Landed.", "Down.", "Wheels down."]}
        report = repeat_report.build_report(rows, lines_by_key, min_uses=5)
        self.assertEqual([r[5] for r in report], ["LaunchVessel"])    # Touchdown was said once: under min_uses
        ratio, uses, pool, distinct, close, key = report[0]
        self.assertEqual((uses, pool, distinct), (10, 2, 1))
        self.assertEqual(close, 9)                                     # the same line came again 9 times inside the window

    def test_mood_variants_count_toward_the_same_key(self):
        rows = [("X", "Hello."), ("X", "Hello."), ("X", "Hi there.")] * 4
        report = repeat_report.build_report(rows, {"Greet": ["Hello."], "Greet_Close": ["Hi there."]}, min_uses=3)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0][2], 2)                              # pool = base + mood lines


if __name__ == "__main__":
    unittest.main()
