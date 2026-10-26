"""Material storage callouts: percentages, batching and the limits on how often she speaks."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from control import material_fill
from control.material_fill import MaterialFill
from core.event_bus import EventBus
from events.registry import load_registry
from journal import materials
from journal.game_state import GameState
from journal.processor import EventProcessor


class Settings:
    def __init__(self, **v):
        self.v = v

    def get(self, key, default=None):
        return self.v.get(key.split(".")[-1], default)


class Narrator:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, fields))
        return True


class Rig:
    def __init__(self, **settings):
        self.bus, self.state, self.narr = EventBus(), GameState(), Narrator()
        self.now = [1000.0]
        self.fill = MaterialFill(self.bus, Settings(**settings), self.narr, lambda: self.state, clock=lambda: self.now[0],
                                 timer_factory=lambda s, f: SimpleNamespace(start=lambda: None, cancel=lambda: None))
        self.fill.attach()

    def have(self, **counts):
        self.state.materials.update({k: v for k, v in counts.items()})

    def pick(self, *names):
        for n in names:
            self.bus.publish("MaterialCollected", {"Name": n, "Count": 1})
        self.fill.flush()

    def keys(self):
        return [k for k, _ in self.narr.said]


class Percent(unittest.TestCase):
    def test_limits_follow_the_grade(self):
        self.assertEqual(materials.limit("iron"), 300)            # grade 1
        self.assertEqual(materials.limit("Polonium"), 150)        # raw grade 4
        self.assertEqual(materials.limit("embeddedfirmware"), 100)  # encoded grade 5
        self.assertIsNone(materials.limit("nonsense"))

    def test_percent(self):
        state = GameState()
        state.materials = {"iron": 246}
        self.assertEqual(materials.percent(state, "iron"), 82)

    def test_journal_lines_keep_the_count(self):
        bus, state = EventBus(), GameState()
        proc = EventProcessor(bus, {}, state, load_registry())
        proc.handle_entry({"event": "Materials", "Raw": [{"Name": "iron", "Count": 100}], "Manufactured": [], "Encoded": []})
        proc.handle_entry({"event": "MaterialCollected", "Category": "Raw", "Name": "iron", "Count": 5})
        self.assertEqual(state.materials["iron"], 105)
        proc.handle_entry({"event": "MaterialDiscarded", "Category": "Raw", "Name": "iron", "Count": 20})
        proc.handle_entry({"event": "Synthesis", "Name": "x", "Materials": [{"Name": "iron", "Count": 5}]})
        proc.handle_entry({"event": "EngineerCraft", "Ingredients": [{"Name": "iron", "Count": 10}]})
        proc.handle_entry({"event": "MaterialTrade", "Paid": {"Material": "iron", "Quantity": 10}, "Received": {"Material": "carbon", "Quantity": 4}})
        self.assertEqual((state.materials["iron"], state.materials["carbon"]), (60, 4))


class Callouts(unittest.TestCase):
    def test_says_the_percent(self):
        r = Rig()
        r.have(iron=246)
        r.pick("iron")
        self.assertEqual(r.narr.said[0][0], "MaterialFill_One")
        self.assertEqual(r.narr.said[0][1]["Percent"], 82)
        self.assertEqual(r.narr.said[0][1]["Material"], "Iron")

    def test_low_stores_are_not_mentioned(self):
        r = Rig()
        r.have(iron=30)
        r.pick("iron")
        self.assertEqual(r.keys(), [])
        r2 = Rig(fill_min_percent=0)
        r2.have(iron=30)
        r2.pick("iron")
        self.assertEqual(r2.keys(), ["MaterialFill_One"])

    def test_a_burst_is_one_line_with_the_fullest_two(self):
        r = Rig()
        r.have(iron=270, carbon=240, nickel=200, lead=100)
        r.pick("iron", "carbon", "nickel", "lead")
        self.assertEqual(r.keys(), ["MaterialFill_Many"])
        self.assertEqual(r.narr.said[0][1]["Material"], "Iron")
        r = Rig()
        r.have(iron=270, carbon=240, lead=50)
        r.pick("iron", "carbon", "lead")
        self.assertEqual(r.keys(), ["MaterialFill_Two"])

    def test_it_needs_ten_more_points_and_a_pause_before_the_same_material_again(self):
        r = Rig()
        r.have(iron=240)                              # 80
        r.pick("iron")
        r.now[0] += 200
        r.have(iron=250)                              # 83: not enough of a rise
        r.pick("iron")
        r.now[0] += 200
        r.have(iron=272)                              # 90
        r.pick("iron")
        self.assertEqual(r.keys(), ["MaterialFill_One", "MaterialFill_One"])

    def test_global_pause_and_ceiling(self):
        r = Rig()
        names = ["iron", "carbon", "nickel", "lead", "sulphur", "phosphorus", "rhenium"]
        for n in names:
            r.have(**{n: 200})
        r.pick("iron")
        r.now[0] += 5                                 # too soon after the last line
        r.pick("carbon")
        self.assertEqual(len(r.narr.said), 1)
        for n in names[1:]:                           # one line every 30 s: the ceiling stops them at five
            r.now[0] += 30
            r.pick(n)
        self.assertEqual(len(r.narr.said), material_fill.MAX_PER_WINDOW)

    def test_full_is_called_out_once(self):
        r = Rig()
        r.have(iron=300)
        r.pick("iron")
        r.pick("iron")
        self.assertEqual(r.keys(), ["MaterialFill_Full"])

    def test_switch_off(self):
        r = Rig(fill_callout=False)
        r.have(iron=290)
        r.pick("iron")
        self.assertEqual(r.keys(), [])

    def test_unknown_material_is_ignored(self):
        r = Rig()
        r.have(mystery=500)
        r.pick("mystery")
        self.assertEqual(r.keys(), [])

    def test_lines_exist(self):
        pack = json.loads(Path("voicepacks/default/materials.json").read_text(encoding="utf-8"))
        for key in ("MaterialFill_One", "MaterialFill_Two", "MaterialFill_Many", "MaterialFill_Full"):
            self.assertIn(key, pack)


if __name__ == "__main__":
    unittest.main()
