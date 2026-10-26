import json
import unittest
from pathlib import Path

from core.event_bus import EventBus
from events import nsp
from events.registry import load_registry
from journal.game_state import GameState
from journal.processor import EventProcessor


def run(entries):
    bus, got = EventBus(), []
    bus.subscribe("*", lambda e: got.append((e.name, e.data)))
    state = GameState()
    state.system = "Test"
    proc = EventProcessor(bus, {}, state, load_registry())
    for e in entries:
        proc.handle_entry(e)
    return got


def codex(name, new=False, **extra):
    entry = {"event": "CodexEntry", "Name_Localised": name, "Category_Localised": "Biological and Geological"}
    if new:
        entry["IsNewEntry"] = True
    entry.update(extra)
    return entry


class Types(unittest.TestCase):
    def test_every_type_matches_its_own_name(self):
        for t in nsp.types():
            self.assertIs(nsp.classify(" ".join(t["match"])) is not None, True, t["key"])
        self.assertEqual(len(nsp.types()), 28)

    def test_names(self):
        for text, key in [("Albulum Bell Mollusc", "bell_mollusc"), ("Caeruleum Lagrange Cloud", "lagrange"),
                          ("Roseum Lagrange Storm Cloud", "lagrange_storm"), ("Albus Ice Crystal", "ice_crystal"),
                          ("Viridis Gyre Tree", "gyre_tree"), ("Purpureum Gourd Mollusc", "gourd_mollusc"),
                          ("Lattice Mineral Sphere", "lattice_sphere"), ("Blatteum Collared Pod", "collared_pod")]:
            self.assertEqual(nsp.classify(text)["key"], key, text)
        for text in ("Bacterium Aurasus", "Fumarole", "Thargoid Scout", ""):
            self.assertIsNone(nsp.classify(text), text)


class Events(unittest.TestCase):
    def test_new_and_seen(self):
        got = run([codex("Albulum Bell Mollusc", new=True), codex("Caeruleum Lagrange Cloud")])
        names = [n for n, _ in got]
        self.assertEqual(names, ["NSPNew", "NSPSeen"])
        self.assertIn("bell-shaped", got[0][1]["Fact"])
        self.assertEqual(got[0][1]["Name"], "Albulum Bell Mollusc")

    def test_plain_codex_entries_still_speak(self):
        self.assertEqual([n for n, _ in run([codex("Bacterium Aurasus", new=True)])], ["CodexEntry"])

    def test_the_same_seen_one_is_only_mentioned_once(self):
        got = run([codex("Caeruleum Lagrange Cloud"), codex("Caeruleum Lagrange Cloud")])
        self.assertEqual([n for n, _ in got], ["NSPSeen"])
        got = run([codex("Caeruleum Lagrange Cloud", new=True), codex("Caeruleum Lagrange Cloud", new=True)])
        self.assertEqual([n for n, _ in got], ["NSPNew", "NSPNew"])

    def test_signal_in_system_once_per_system(self):
        sig = {"event": "FSSSignalDiscovered", "SystemAddress": 1, "SignalName": "$Fixed_Event_Life_Cloud;", "SignalName_Localised": "Notable stellar phenomena"}
        got = run([sig, sig, dict(sig, SystemAddress=2)])
        self.assertEqual([n for n, _ in got], ["NSPInSystem", "NSPInSystem"])
        plain = {"event": "FSSSignalDiscovered", "SystemAddress": 1, "SignalName": "$NumberStation;"}
        self.assertEqual([n for n, _ in run([plain])], ["FSSSignalDiscovered"])

    def test_mood_rules_and_lines(self):
        rules = json.loads(Path("config/mood_rules.json").read_text(encoding="utf-8"))["rules"]
        by = {r["id"]: r for r in rules}
        self.assertGreater(by["nsp_new"]["delta"], by["nsp_seen"]["delta"] > 0 and by["nsp_seen"]["delta"])
        pack = json.loads(Path("voicepacks/default/nsp.json").read_text(encoding="utf-8"))
        for key in ("NSPNew", "NSPSeen", "NSPInSystem"):
            self.assertGreaterEqual(len(pack[key]), 7)


if __name__ == "__main__":
    unittest.main()
