import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from control.limpet_reminder import LimpetReminder, has_mining_kit, limpets_carried
from core.event_bus import EventBus
from events.loadout import Loadout
from journal.game_state import GameState

KIT = ["int_refinery_size2_class1", "int_dronecontrol_collection_size1_class1", "int_cargorack_size5_class1"]


class Settings:
    def __init__(self, on=True):
        self.on = on

    def get(self, key, default=None):
        return self.on if key == "mining.limpet_reminder" else default


class Narrator:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append(key)


def setup(modules, cargo=None, on=True):
    folder = tempfile.mkdtemp()
    if cargo is not None:
        Path(folder, "Cargo.json").write_text(json.dumps({"Inventory": [{"Name": "drones", "Count": cargo}]}))
    state = SimpleNamespace(modules=modules)
    narrator = Narrator()
    bus = EventBus()
    LimpetReminder(bus, Settings(on), narrator, lambda: state, lambda: folder).attach()
    return bus, narrator


def dock(bus, services=None):
    bus.publish("Docked", {"StationServices": services} if services else {})


class Reminder(unittest.TestCase):
    def test_kit_needs_all_three(self):
        self.assertTrue(has_mining_kit(KIT))
        for missing in range(3):
            self.assertFalse(has_mining_kit([m for i, m in enumerate(KIT) if i != missing]))
        self.assertTrue(has_mining_kit(KIT[:2] + ["int_corrosionproofcargorack_size4_class1"]))

    def test_reminds_with_kit(self):
        bus, narrator = setup(KIT, cargo=0)
        dock(bus)
        self.assertEqual(narrator.said, ["Mining_LimpetReminder"])

    def test_silent_without_kit_or_when_off_or_stocked(self):
        for kwargs in ({"modules": KIT[:2]}, {"modules": KIT, "on": False}, {"modules": KIT, "cargo": 120}):
            bus, narrator = setup(**kwargs)
            dock(bus)
            self.assertEqual(narrator.said, [], kwargs)

    def test_silent_without_market(self):
        bus, narrator = setup(KIT)
        dock(bus, ["dock", "repair"])
        self.assertEqual(narrator.said, [])
        dock(bus, ["dock", "commodities"])
        self.assertEqual(len(narrator.said), 1)

    def test_loadout_learns_modules(self):
        state = GameState()
        Loadout().update_state({"Modules": [{"Item": "int_refinery_size1_class1"}, {"Item": "x"}]}, state)
        self.assertEqual(state.modules, ["int_refinery_size1_class1", "x"])

    def test_cargo_unreadable(self):
        self.assertIsNone(limpets_carried(tempfile.mkdtemp()))

    def test_line_exists(self):
        data = json.loads(Path("voicepacks/default/mining2.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["Mining_LimpetReminder"]), 5)


if __name__ == "__main__":
    unittest.main()
