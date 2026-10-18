import unittest
from pathlib import Path

from core import paths
from core.identity import assistant_name, commander_sex, personalise, sex_label, wake_phrase
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.flavour import Flavour
from tests.test_flavour import Rng


def settings(**values):
    s = Settings(Path("nope_settings.json")).load()
    for k, v in values.items():
        s.set(k.replace("__", "."), v)
    return s


class IdentityTests(unittest.TestCase):
    def test_name_and_wake_word(self):
        s = settings()
        self.assertEqual(assistant_name(s), "Starling")
        self.assertEqual(wake_phrase(s), "Starling")
        s.set("app.name", "Nova")
        self.assertEqual(wake_phrase(s), "Nova")                  # follows her name
        s.set("stt.wake_phrase", "Computer")
        self.assertEqual(wake_phrase(s), "Computer")
        s.set("stt.wake_phrase", "Tetko")                          # an old saved setting follows the new name
        self.assertEqual(wake_phrase(s), "Nova")

    def test_name_token(self):
        s = settings(app__name="Nova")
        self.assertEqual(personalise("I'm @NAME@ and @NAME@ is here.", s), "I'm Nova and Nova is here.")
        self.assertEqual(personalise("No token.", s), "No token.")

    def test_dialogue_uses_the_token_not_a_fixed_name(self):
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        everything = [l.text for ls in d.lines.values() for l in ls]
        self.assertTrue(any("@NAME@" in t for t in everything))
        self.assertFalse(any("Tetko" in t for t in everything))

    def test_sex_labels(self):
        self.assertEqual(sex_label(settings()), "")
        self.assertEqual(sex_label(settings(player__sex="female")), "Female")
        self.assertEqual(commander_sex(settings(player__sex="nonsense")), "neutral")


class GenderedSpeechTests(unittest.TestCase):
    def names_for(self, sex, mood="Friendly"):
        s = settings(player__sex=sex, personality__mood_mode="fixed", personality__mood=mood,
                     personality__remarks="often")
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        seen = set()
        for seed in range(80):
            f = Flavour(d, s, rng=Rng(0.0), clock=lambda: 0.0)
            f.rng = __import__("random").Random(seed)
            f._last_remark = None
            out = f.apply("Docked, Commander.", "normal")
            seen.add(out)
        return " ".join(seen).lower()

    def test_male_commander_gets_handsome_not_beautiful(self):
        text = self.names_for("male")
        self.assertIn("handsome", text)
        self.assertNotIn("beautiful", text)

    def test_female_commander_gets_beautiful_not_handsome(self):
        text = self.names_for("female")
        self.assertIn("beautiful", text)
        self.assertNotIn("handsome", text)

    def test_neutral_gets_neither(self):
        text = self.names_for("neutral")
        for word in ("handsome", "beautiful", "princess", "cowboy", "cowgirl", "tiger", "angel"):
            self.assertNotIn(word, text)

    def test_snide_names_follow_sex_too(self):
        self.assertNotIn("cowgirl", self.names_for("male", "Sarcastic"))
        self.assertNotIn("cowboy", self.names_for("female", "Sarcastic"))


if __name__ == "__main__":
    unittest.main()
