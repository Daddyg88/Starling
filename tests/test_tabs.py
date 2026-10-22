import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality import categories, line_keys
from personality.dialogue import DialogueManager
from personality.speaker import EventSpeaker
from tests.helpers import make_processor
from tests.test_dialogue import FakeSpeech
from ui.settings_model import build_pages


def ev(name, priority="normal", **data):
    return SimpleNamespace(name=name, data=data, priority=priority)


class TabLayoutTests(unittest.TestCase):
    def pages(self):
        return {p.id: [f.key for f in p.fields] for p in build_pages()}

    def test_the_six_tabs_exist_with_their_switch_and_toggles(self):
        pages = self.pages()
        for tab in ("combat", "exploration", "exobiology", "mining", "trading", "antixeno"):
            self.assertIn(tab, pages)
            self.assertEqual(pages[tab][0], "talk." + tab)
        self.assertIn("combat_assist.pips", pages["combat"])
        self.assertIn("combat_assist.pips_analysis", pages["combat"])
        self.assertIn("combat_assist.heat_sink", pages["combat"])
        self.assertIn("autohonk.mode", pages["exploration"])
        self.assertIn("ask.scan_prompts", pages["exploration"])
        self.assertIn("ask.bio_prompts", pages["exobiology"])
        self.assertIn("mining.chatter", pages["mining"])
        self.assertEqual(len([k for k in pages["mining"] if k.startswith("mining.fav")]), 10)
        self.assertIn("mining.prices", pages["trading"])

    def test_moved_toggles_are_not_left_behind_in_other_pages(self):
        pages = self.pages()
        for key in ("combat_assist.pips", "autohonk.mode", "ask.bio_prompts", "ask.scan_prompts", "mining.prices"):
            owners = [p for p, keys in pages.items() if key in keys]
            self.assertEqual(len(owners), 1, key)

    def test_no_setting_appears_twice(self):
        keys = [k for ks in self.pages().values() for k in ks]
        self.assertEqual(len(keys), len(set(keys)))


class MergedPageTests(unittest.TestCase):
    def test_small_pages_live_inside_bigger_ones(self):
        from ui.settings_model import SettingsModel
        from core.settings import Settings
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            model = SettingsModel(Settings(Path(tmp) / "s.json").load())
        shown = [p.id for p in model.sidebar_pages]
        for gone in ("listening", "controls", "chat", "memory", "bookmarks"):
            self.assertNotIn(gone, shown)
        homes = {p.id: p.parent for p in model.pages if p.parent}
        self.assertEqual(homes, {"listening": "voice", "controls": "game", "chat": "personality",
                                 "memory": "personality", "bookmarks": "navigation"})
        for parent in set(homes.values()):
            self.assertIn(parent, shown)
        self.assertEqual(shown[-1], "developer")                  # the Developer tab holds the tests


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()

    def test_every_listed_event_has_a_tab(self):
        self.assertEqual(categories.category_of("ShipTargeted"), "combat")
        self.assertEqual(categories.category_of("Scan"), "exploration")
        self.assertEqual(categories.category_of("ScanOrganic"), "exobiology")
        self.assertEqual(categories.category_of("MiningRefined"), "mining")
        self.assertEqual(categories.category_of("ShipyardBuy"), "trading")
        self.assertEqual(categories.category_of("ShipTargeted", {"Announce": "thargoid"}), "antixeno")
        self.assertEqual(categories.category_of("FSSBodySignals", {"Biological": True}), "exobiology")
        self.assertIsNone(categories.category_of("FSDJump"))

    def test_off_silences_that_tab_only(self):
        self.settings.set("talk.mining", False)
        self.assertFalse(categories.allowed(ev("MiningRefined"), self.settings))
        self.assertTrue(categories.allowed(ev("Bounty"), self.settings))
        self.assertTrue(categories.allowed(ev("FSDJump"), self.settings))

    def test_safety_warnings_are_never_silenced(self):
        for tab in categories.TABS:
            self.settings.set("talk." + tab, False)
        self.assertTrue(categories.allowed(ev("UnderAttack", "critical"), self.settings))
        self.assertTrue(categories.allowed(ev("ShipTargeted", "critical"), self.settings))

    def test_the_speaker_obeys_the_switch(self):
        speech = FakeSpeech()
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"], rng=random.Random(1)).load()
        speaker = EventSpeaker(EventBus(), speech, dialogue, self.settings)
        speaker.on_event(ev("AsteroidCracked", "low", Body="x"))
        self.assertEqual(len(speech.said), 1)
        self.settings.set("talk.mining", False)
        speaker._last_spoken.clear()
        speaker.on_event(ev("AsteroidCracked", "low", Body="x"))
        self.assertEqual(len(speech.said), 1)


class ThargoidTests(unittest.TestCase):
    def target(self, **extra):
        processor, _bus, heard = make_processor()
        entry = {"event": "ShipTargeted", "TargetLocked": True, "ScanStage": 1}
        entry.update(extra)
        processor.handle_line(json.dumps(entry))
        return heard[-1]

    def test_thargoid_ships_are_named_even_with_hardpoints_in(self):
        for ship, local in (("cyclops", "Cyclops"), ("scout_q", "Thargoid Scout"), ("basilisk", None), ("hydra", "Hydra")):
            event = self.target(Ship=ship, Ship_Localised=local) if local else self.target(Ship=ship)
            self.assertEqual(event.data["Announce"], "thargoid", ship)
            self.assertEqual(line_keys.keys_for(event), ["ShipTargeted_Thargoid"])
        self.assertTrue(self.target(Ship="cyclops").data["Ship"])

    def test_player_scout_ships_are_not_thargoids(self):
        self.assertNotEqual(self.target(Ship="asp_scout", Ship_Localised="Asp Scout").data["Announce"], "thargoid")
        self.assertNotEqual(self.target(Ship="cobramkiii").data["Announce"], "thargoid")

    def test_lines_fill_in(self):
        pack = json.load(open(paths.VOICEPACKS_DIR / "default" / "combat.json", encoding="utf-8"))
        for key in [k for k in pack if k.startswith("ShipTargeted_Thargoid")]:
            for item in pack[key]:
                (item["text"] if isinstance(item, dict) else item).format(Ship="Cyclops")


if __name__ == "__main__":
    unittest.main()
