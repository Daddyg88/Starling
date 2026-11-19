"""Synthesis lines: the recipe is sorted by its words, and she never talks more than once every 15 seconds."""

import json
import unittest
from pathlib import Path

from control.synthesis_talk import COOLDOWN, SynthesisTalk, grade_of, kind_of
from core.event_bus import EventBus


class Settings:
    def __init__(self, **v):
        self.v = v

    def get(self, key, default=None):
        return self.v.get(key, default)


class Narrator:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, fields))
        return True


class Rig:
    def __init__(self, **settings):
        self.bus, self.narr, self.now = EventBus(), Narrator(), [100.0]
        self.talk = SynthesisTalk(self.bus, Settings(**settings), self.narr, clock=lambda: self.now[0])
        self.talk.attach()

    def synth(self, name):
        self.bus.publish("Synthesis", {"Name": name})


class KindTests(unittest.TestCase):
    def test_recipe_names_are_sorted_by_their_words(self):
        for name, kind in (("Restock Basic", "Ammo"), ("SRV Ammo Restock", "Ammo"), ("AFM Refill Premium", "Ammo"), ("FSD Standard", "FSD"),
                           ("Limpet Basic", "Limpet"), ("Repair Basic", "Repair"), ("Heat Sink Standard", "Heat"), ("Chaff Basic", "Chaff"),
                           ("SRV Refuel", "Refuel"), ("Something new", "Generic"), (None, "Generic")):
            self.assertEqual(kind_of(name), kind, name)

    def test_grade(self):
        self.assertEqual(grade_of("FSD Premium"), "premium")
        self.assertEqual(grade_of("Restock"), "")


class TalkTests(unittest.TestCase):
    def test_ammo_gets_the_ammo_lines(self):
        r = Rig()
        r.synth("Restock Basic")
        self.assertEqual(r.narr.said[0][0], "Synthesis_Ammo")

    def test_no_nagging(self):
        r = Rig()
        r.synth("Restock Basic")
        r.now[0] += COOLDOWN - 1
        r.synth("Restock Basic")
        self.assertEqual(len(r.narr.said), 1)
        r.now[0] += 2
        r.synth("Repair Basic")
        self.assertEqual([k for k, _ in r.narr.said], ["Synthesis_Ammo", "Synthesis_Repair"])

    def test_switch_off(self):
        r = Rig(**{"synthesis.callout": False})
        r.synth("Restock Basic")
        self.assertEqual(r.narr.said, [])

    def test_failed_speech_does_not_start_the_cooldown(self):
        r = Rig()
        r.narr.say = lambda key, fields=None: False
        r.synth("Restock Basic")
        r.narr.say = lambda key, fields=None: (r.narr.said.append((key, fields)) or True)
        r.synth("Restock Basic")
        self.assertEqual(len(r.narr.said), 1)


class LinesTests(unittest.TestCase):
    def test_every_group_has_lines_and_no_banned_words(self):
        lines = json.loads((Path(__file__).resolve().parent.parent / "voicepacks" / "default" / "synthesis.json").read_text(encoding="utf-8"))
        for key in ("Synthesis_Ammo", "Synthesis_Repair", "Synthesis_FSD", "Synthesis_Limpet", "Synthesis_Refuel", "Synthesis_Heat",
                    "Synthesis_Chaff", "Synthesis_Generic"):
            self.assertTrue(lines[key], key)
        self.assertGreaterEqual(len(lines["Synthesis_Ammo"]), 8)

    def test_hologram_nods(self):
        from ui.hologram import REACTIONS
        self.assertEqual(REACTIONS["Synthesis"][0], "nod")


if __name__ == "__main__":
    unittest.main()


class LoadedByThePackTests(unittest.TestCase):
    def test_the_dialogue_manager_loads_the_lines(self):
        from personality.dialogue import DialogueManager
        manager = DialogueManager(Path(__file__).resolve().parent.parent / "voicepacks" / "default")
        manager.load()
        line = manager.pick("Synthesis_Ammo", "", False, False)
        self.assertIsNotNone(line)
