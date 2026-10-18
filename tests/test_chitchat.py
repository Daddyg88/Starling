import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality.chitchat import ChitChat, FREQUENCY
from personality.dialogue import DialogueManager


class Speech:
    def __init__(self, accept=True):
        self.said, self.accept = [], accept

    def say(self, **kw):
        if self.accept:
            self.said.append(kw)
        return self.accept


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.bus = EventBus()
        self.t = [1000.0]
        self.speech = Speech()
        self.state = SimpleNamespace(docked=False, in_supercruise=False)
        self.active = [True]
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", rng=random.Random(3)).load()
        self.chat = ChitChat(self.bus, self.speech, self.dialogue, self.settings, lambda: self.state, lambda: self.active[0],
                             clock=lambda: self.t[0], rng=random.Random(1))
        self.chat.attach()

    def later(self, seconds):
        self.t[0] += seconds

    def fire(self, name, **data):
        self.bus.publish(name, data)


class TimingTests(Base):
    def test_quiet_start(self):
        self.assertIsNone(self.chat.tick())
        self.later(100)
        self.assertIsNone(self.chat.tick())

    def test_chats_after_a_quiet_spell(self):
        self.later(FREQUENCY["normal"][1] + 10)
        text = self.chat.tick()
        self.assertTrue(text)
        self.assertEqual(self.speech.said[0]["priority"], "low")

    def test_not_again_straight_away(self):
        self.later(2000)
        self.assertTrue(self.chat.tick())
        self.later(60)
        self.assertIsNone(self.chat.tick())
        self.later(FREQUENCY["normal"][1] * 2 + 10)
        self.assertTrue(self.chat.tick())

    def test_speaking_resets_the_quiet_timer(self):
        self.later(2000)
        self.fire("speech.finished", text="x")
        self.assertIsNone(self.chat.tick())

    def test_no_chat_when_game_not_active(self):
        self.later(2000)
        self.active[0] = False
        self.assertIsNone(self.chat.tick())

    def test_switched_off(self):
        self.later(2000)
        self.settings.set("chitchat.enabled", False)
        self.assertIsNone(self.chat.tick())

    def test_info_style_never_chats(self):
        self.later(2000)
        self.settings.set("personality.style", "info")
        self.assertIsNone(self.chat.tick())

    def test_not_after_an_alarm(self):
        self.later(2000)
        self.fire("UnderAttack", Target="You")
        self.later(30)
        self.assertIsNone(self.chat.tick())
        self.later(400)
        self.assertTrue(self.chat.tick())

    def test_busy_speaker_means_try_later(self):
        self.later(2000)
        self.speech.accept = False
        self.assertIsNone(self.chat.tick())
        self.speech.accept = True
        self.later(15)
        self.assertTrue(self.chat.tick())

    def test_rarely_waits_longer_than_often(self):
        self.later(500)
        self.settings.set("chitchat.frequency", "rarely")
        self.assertIsNone(self.chat.tick())
        self.settings.set("chitchat.frequency", "often")
        self.later(0)
        self.assertTrue(self.chat.due() or self.t[0] - self.chat.last_chat < FREQUENCY["often"][1])


class ModeTests(Base):
    def test_pool_follows_the_mode(self):
        self.assertEqual(self.chat.pool_key(), "ChitChat_General")
        self.fire("CombatModeOn")
        self.assertEqual(self.chat.pool_key(), "ChitChat_Combat")
        self.fire("AnalysisModeOn")
        self.assertEqual(self.chat.pool_key(), "ChitChat_Analysis")
        self.state.docked = True
        self.assertEqual(self.chat.pool_key(), "ChitChat_Docked")
        self.state.docked = False
        self.fire("CombatModeOn")
        self.assertEqual(self.chat.pool_key(), "ChitChat_Combat")

    def test_supercruise_pool(self):
        self.state.in_supercruise = True
        self.assertEqual(self.chat.pool_key(), "ChitChat_Supercruise")

    def test_combat_chat_comes_sooner(self):
        normal_quiet = self.chat._timing()[0]
        self.fire("CombatModeOn")
        self.assertLess(self.chat._timing()[0], normal_quiet)

    def test_every_pool_has_lines(self):
        for key in ("ChitChat_General", "ChitChat_Combat", "ChitChat_Analysis", "ChitChat_Docked", "ChitChat_Supercruise"):
            self.assertGreaterEqual(len(self.dialogue.pool(key, "", False, False)), 4, key)

    def test_combat_chat_is_about_combat(self):
        self.fire("CombatModeOn")
        self.later(3000)
        text = self.chat.tick()
        combat_lines = {l.text for l in self.dialogue.pool("ChitChat_Combat", "", False, False)}
        combat_lines |= {l.text for l in self.dialogue.pool("ChitChat_Combat", "Sarcastic", False, False)}
        self.assertIn(text, combat_lines)


if __name__ == "__main__":
    unittest.main()
