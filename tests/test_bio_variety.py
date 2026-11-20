"""A long trip through the same species keeps sounding fresh: facts are cycled, not repeated, and the wording pools are wide."""

import json
import random
import unittest

from core import paths
from journal.exobiology import BioInfo
from personality.line_keys import _keys_for
from core.event_bus import Event


def info(seed=1):
    return BioInfo(paths.CONFIG_DIR / "bio_info.json", random.Random(seed), paths.CONFIG_DIR / "bio_rules.json")


def values():
    data = json.loads((paths.CONFIG_DIR / "exobiology_values.json").read_text(encoding="utf-8"))
    return ({k.lower(): v for k, v in data["values"].items()}, {k.lower(): v for k, v in data["colony_distance_m"].items()})


class CycleTests(unittest.TestCase):
    def test_every_fact_is_told_before_any_is_repeated(self):
        prices, metres = values()
        bio = info()
        pool = bio.pool("Aleoida Arcus", "Aleoida", prices, metres)
        self.assertGreaterEqual(len(pool), 7)
        told = []
        for _ in range(len(pool)):
            told.append(bio.about("Aleoida Arcus", "Aleoida", 1, prices, metres))
        self.assertEqual(sorted(told), sorted(pool))

    def test_two_facts_in_one_go_are_different(self):
        prices, metres = values()
        for seed in range(30):
            text = info(seed).about("Aleoida Arcus", "Aleoida", 2, prices, metres)
            sentences = [s for s in text.split(". ") if s]
            self.assertEqual(len(sentences), len(set(sentences)))

    def test_the_round_after_the_last_fact_does_not_start_with_the_same_one(self):
        prices, metres = values()
        bio = info()
        size = len(bio.pool("Aleoida Arcus", "Aleoida", prices, metres))
        first_round = [bio.about("Aleoida Arcus", "Aleoida", 1, prices, metres) for _ in range(size)]
        self.assertNotEqual(bio.about("Aleoida Arcus", "Aleoida", 1, prices, metres), first_round[-1])

    def test_a_species_with_no_facts_says_nothing(self):
        self.assertEqual(info().about("Nothing Known", "Nothing"), "")


class WorkedOutFactTests(unittest.TestCase):
    def test_habitat_facts_come_from_the_rules(self):
        prices, metres = values()
        facts = info().habitat_facts("Aleoida Arcus", prices, metres, "Aleoida")
        text = " ".join(facts)
        self.assertIn("0.275 g", text)
        self.assertIn("between 175 and 180 kelvin", text)
        self.assertIn("150 metres", text)

    def test_no_atmosphere_species(self):
        facts = info().habitat_facts("Amphora Plant")
        self.assertTrue(any("no atmosphere" in f for f in facts))

    def test_unknown_species_has_no_worked_out_facts(self):
        self.assertEqual(info().habitat_facts("Nobody Here"), [])


class LineChoiceTests(unittest.TestCase):
    def test_third_sample_with_a_fact_uses_the_about_lines_first(self):
        data = {"ScanType": "Sample", "SampleNumber": 3, "About": "x"}
        self.assertEqual(_keys_for(Event("ScanOrganic", data))[0], "ScanOrganic_ThirdAbout")
        self.assertEqual(_keys_for(Event("ScanOrganic", {"ScanType": "Sample", "SampleNumber": 3})), ["ScanOrganic_Third"])


class PoolSizeTests(unittest.TestCase):
    def test_pools_are_wide(self):
        from personality.dialogue import DialogueManager
        manager = DialogueManager(paths.VOICEPACKS_DIR / "default")
        manager.load()
        for key, minimum in (("ScanOrganic_Log", 14), ("ScanOrganic_Sample", 15), ("ScanOrganic_SampleAbout", 12), ("ScanOrganic_Third", 13),
                             ("ScanOrganic_ThirdAbout", 6), ("ScanOrganic_Analyse", 18)):
            self.assertGreaterEqual(len(manager.lines.get(key, [])), minimum, key)


if __name__ == "__main__":
    unittest.main()
