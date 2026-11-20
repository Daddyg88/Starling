"""Funny remarks about how each kind of life looks: after the first sample, cheeky ones only with 'Flirty and naughty' on."""

import json
import unittest

from core import paths
from journal.bio_predict import BioPredictor, BioCodex, genus_key, load_rules
from journal.exobiology import ExobiologyTracker
from personality.dialogue import DialogueManager
from personality.line_keys import _keys_for
from core.event_bus import Event


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class Fixed:
    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.0


def predictor(**settings):
    tracker = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
    return BioPredictor(tracker, codex=BioCodex(), settings=Settings(settings))


def scan(stage, species="Aleoida Arcus", genus="Aleoida"):
    return {"event": "ScanOrganic", "ScanType": stage, "Species_Localised": species, "Genus_Localised": genus, "Body": 5, "SystemAddress": 1}


class WhenTests(unittest.TestCase):
    def test_first_sample_gets_a_look_remark(self):
        p = predictor()
        p.look_rng = Fixed(0.1)
        events = p.note_organic(scan("Log"))
        self.assertEqual([name for name, _ in events], ["BioLook"])
        self.assertEqual(events[0][1]["Genus"], "aleoida")
        self.assertFalse(events[0][1]["Naughty"])

    def test_later_samples_do_not(self):
        p = predictor()
        p.look_rng = Fixed(0.1)
        self.assertEqual(p.note_organic(scan("Sample")), [])
        self.assertEqual(p.note_organic(scan("Sample")), [])

    def test_not_every_time(self):
        p = predictor()
        p.look_rng = Fixed(0.99)
        self.assertEqual(p.note_organic(scan("Log")), [])

    def test_switch_off(self):
        p = predictor(**{"exobiology.looks": False})
        p.look_rng = Fixed(0.1)
        self.assertEqual(p.note_organic(scan("Log")), [])

    def test_cheeky_only_with_the_naughty_switch(self):
        p = predictor(**{"personality.innuendo": True})
        p.look_rng = Fixed(0.1, 0.1)
        self.assertTrue(p.note_organic(scan("Log"))[0][1]["Naughty"])
        q = predictor()
        q.look_rng = Fixed(0.1, 0.1)
        self.assertFalse(q.note_organic(scan("Log"))[0][1]["Naughty"])

    def test_naughty_switch_on_still_gives_some_clean_ones(self):
        p = predictor(**{"personality.innuendo": True})
        p.look_rng = Fixed(0.1, 0.95)
        self.assertFalse(p.note_organic(scan("Log"))[0][1]["Naughty"])


class LineTests(unittest.TestCase):
    def setUp(self):
        self.lines = json.loads((paths.VOICEPACKS_DIR / "default" / "bio_looks.json").read_text(encoding="utf-8"))

    def test_every_genus_has_clean_and_cheeky_lines(self):
        genera = {genus_key(r["g"]) for r in load_rules()}
        self.assertGreaterEqual(len(genera), 20)
        for g in genera:
            self.assertGreaterEqual(len(self.lines.get("BioLook_" + g, [])), 5, g)
            self.assertGreaterEqual(len(self.lines.get("BioLook_" + g + "_Naughty", [])), 4, g)

    def test_line_keys(self):
        self.assertEqual(_keys_for(Event("BioLook", {"Genus": "osseu", "Naughty": True})), ["BioLook_osseu_Naughty", "BioLook_osseu"])
        self.assertEqual(_keys_for(Event("BioLook", {"Genus": "osseu", "Naughty": False})), ["BioLook_osseu"])

    def test_nothing_in_them_is_explicit_or_uses_strong_language(self):
        banned = ("fuck", "shit", "cock", "dick", "pussy", "cunt", "bitch", "cum ", "sex")
        for key, items in self.lines.items():
            if key == "_help":
                continue
            for line in items:
                self.assertFalse(any(b in line.lower() for b in banned), line)
                self.assertLess(len(line), 190, line)

    def test_the_dialogue_manager_loads_them(self):
        manager = DialogueManager(paths.VOICEPACKS_DIR / "default")
        manager.load()
        self.assertTrue(manager.pick("BioLook_osseu_Naughty", "", False, False))
        self.assertTrue(manager.pick("BioLook_osseu", "", False, False))


if __name__ == "__main__":
    unittest.main()
