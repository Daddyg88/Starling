"""Less repetition on long sessions: jet cone boosts, neutron jumps, and the no-repeat memory."""

import json
import random
import re
import unittest
from unittest import mock

from events import jet_cone_boost
from personality import line_keys
from tests.helpers import make_processor
from tests.test_dialogue import real_dialogue


def boost():
    return json.dumps({"event": "JetConeBoost", "BoostValue": 4.0})


def spoken(heard):
    return [e for e in heard if e.name == "JetConeBoost"]


class JetCone(unittest.TestCase):
    def test_no_wheee_anywhere(self):
        d = real_dialogue()
        for key in ("JetConeBoost", "JetConeBoost_First", "JetConeBoost_Milestone", "JetConeBoost_Sarcastic", "JetConeBoost_Close"):
            for line in d.lines[key]:
                self.assertIsNone(re.search(r"\bwh?ee+\b|\bwoo+\b", line.text.lower()), line.text)

    def test_every_boost_is_published_but_few_are_spoken(self):
        processor, bus, heard = make_processor()
        with mock.patch.object(jet_cone_boost.random, "random", return_value=0.99):      # the dice say: stay quiet
            for _ in range(60):
                processor.handle_entry(json.loads(boost()))
        events = spoken(heard)
        self.assertEqual(len(events), 60)                                    # the route follower sees them all
        said = [e for e in events if line_keys.keys_for(e)]
        self.assertEqual([e.data["Count"] for e in said], [1, 10, 25, 50])   # first, and the round numbers

    def test_a_new_run_starts_after_a_gap(self):
        processor, bus, heard = make_processor()
        processor.handle_entry(json.loads(boost()))
        processor.state.jet_boost_time -= jet_cone_boost.RUN_GAP_SECONDS + 5
        processor.handle_entry(json.loads(boost()))
        self.assertEqual([e.data["Count"] for e in spoken(heard)], [1, 1])

    def test_keys(self):
        class E:
            name = "JetConeBoost"
            data = {"Announce": "milestone", "Count": 10}
        self.assertEqual(line_keys.keys_for(E()), ["JetConeBoost_Milestone"])
        E.data = {"Announce": ""}
        self.assertEqual(line_keys.keys_for(E()), [])


class Pools(unittest.TestCase):
    def test_neutron_and_white_dwarf_pools_are_big(self):
        d = real_dialogue()
        self.assertGreaterEqual(len(d.lines["StartJump_Neutron"]), 60)
        self.assertGreaterEqual(len(d.lines["StartJump_WhiteDwarf"]), 30)

    def test_fifty_neutron_jumps_rarely_repeat(self):
        d = real_dialogue()
        d.rng = random.Random(7)
        picks = [d.pick("StartJump_Neutron").text for _ in range(50)]
        self.assertEqual(len(picks), len(set(picks)))

    def test_big_pools_remember_most_of_their_lines(self):
        d = real_dialogue()
        d.pick("StartJump_Neutron")
        self.assertGreaterEqual(d._recent["StartJump_Neutron"].maxlen, 30)


if __name__ == "__main__":
    unittest.main()
