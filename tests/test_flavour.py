import random
import unittest
from pathlib import Path

from core import paths
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.flavour import Flavour


class Rng(random.Random):
    """Always 'rolls' the same number, so tests are predictable."""
    def __init__(self, value=0.0):
        super().__init__(1)
        self.value = value

    def random(self):
        return self.value


def make(mood="Friendly", mature=False, style="personality", remarks="often", carried=0, roll=0.0):
    s = Settings(Path("nope_settings.json")).load()
    s.set("personality.mood_mode", "fixed")
    s.set("personality.mood", mood)
    s.set("speech.allow_mature", mature)
    s.set("personality.style", style)
    s.set("personality.remarks", remarks)
    s.set("personality.dark_humour", False)       # dark humour has its own tests
    d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
    t = [0.0]
    f = Flavour(d, s, lambda: carried, rng=Rng(roll), clock=lambda: t[0])
    f.t = t
    return f, d


def texts(d, key):
    return {l.text for l in d.lines.get(key, [])}


class FlavourTests(unittest.TestCase):
    def test_critical_is_never_touched(self):
        f, _ = make()
        self.assertEqual(f.apply("Shields down, Commander.", "critical"), "Shields down, Commander.")

    def test_info_style_adds_nothing(self):
        f, _ = make(style="info")
        self.assertEqual(f.apply("Docked, Commander.", "normal"), "Docked, Commander.")

    def test_good_mood_gets_cute_name_and_remark(self):
        f, d = make("Friendly")
        out = f.apply("Docked, Commander.", "normal")
        name, remark = out.replace("Docked, ", "").split(". || ")
        self.assertIn(name, texts(d, "PetName_Cute") | texts(d, "PetName_Neutral"))
        self.assertIn(remark, texts(d, "Remark_Cute") | texts(d, "Remark_Dry"))

    def test_bad_mood_is_snide_without_strong_language(self):
        f, d = make("Frustrated", mature=False)
        out = f.apply("Docked, Commander.", "normal")
        remark = out.split(" || ")[1]
        self.assertIn(remark, texts(d, "Remark_Snide") | texts(d, "Remark_Dry"))
        self.assertNotIn(remark, texts(d, "Remark_Sweary"))

    def test_bad_mood_swears_only_when_allowed(self):
        f, d = make("Frustrated", mature=True, roll=0.0)
        out = f.apply("Docked.", "normal")
        self.assertIn(out.split(" || ")[1], texts(d, "Remark_Sweary"))

    def test_rich_commander_gets_affection(self):
        f, d = make("Sarcastic", carried=600000000)
        out = f.apply("Docked, Commander.", "normal")
        self.assertIn(out.split(" || ")[1], texts(d, "Remark_Affection"))
        self.assertIn(out.split(",")[1].split(".")[0].strip(), texts(d, "PetName_Affection"))

    def test_not_rich_below_limit(self):
        f, _ = make(carried=499999999)
        self.assertFalse(f.rich())

    def test_remarks_off_and_cooldown(self):
        f, _ = make(remarks="off")
        self.assertNotIn("||", f.apply("Docked.", "normal"))
        f, _ = make(remarks="often")
        self.assertIn("||", f.apply("Docked.", "normal"))
        self.assertNotIn("||", f.apply("Undocked.", "normal"))      # too soon
        f.t[0] += 60
        self.assertIn("||", f.apply("Undocked.", "normal"))

    def test_beats_and_placeholders_left_alone(self):
        f, _ = make()
        self.assertEqual(f.apply("Four || three || two || one", "normal"), "Four || three || two || one")
        self.assertEqual(f.apply("Fuel at {fuel_percent}.", "normal"), "Fuel at {fuel_percent}.")

    def test_commander_name_not_replaced(self):
        f, _ = make(remarks="off")
        self.assertEqual(f.apply("Welcome, Commander Jameson.", "normal"), "Welcome, Commander Jameson.")

    def test_no_mature_line_without_permission(self):
        f, d = make("Frustrated", mature=False)
        for _ in range(60):
            f.t[0] += 100
            f.rng = random.Random(_)
            out = f.apply("Docked, Commander.", "normal")
            for line in d.lines["Remark_Sweary"] + d.lines["PetName_Sweary"]:
                self.assertNotIn(line.text, out)

    def test_extra_mood_lines_are_loaded_and_gated(self):
        _, d = make()
        clean = d.pool("Docked", "Frustrated", False, False)
        self.assertTrue(clean and all(not l.mature for l in clean))
        self.assertTrue(any(l.mature for l in d.pool("Docked", "Frustrated", True, False)))
        self.assertFalse(any(k.startswith(("HullDamage", "ShieldsDown", "Interdicted")) and k.endswith("Frustrated")
                             and any(l.mature for l in v) for k, v in d.lines.items() if "Critical" in k))


if __name__ == "__main__":
    unittest.main()
