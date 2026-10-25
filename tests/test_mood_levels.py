import json
import tempfile
import unittest
from pathlib import Path

from core.event_bus import EventBus
from core.settings import Settings
from personality import mood_engine
from personality.mood_engine import LEVELS, MoodEngine, effective_level


def engine(scale=5, save=None, clock=None):
    settings = Settings(Path("nope.json")).load()
    kwargs = {"save_path": save} if save else {"persist": False}
    return MoodEngine(EventBus(), settings, scale=scale, clock=clock or (lambda: 1000.0), **kwargs), settings


class LevelTests(unittest.TestCase):
    def test_every_mood_has_five_levels(self):
        e, _ = engine()
        for score, band in ((-500, "Upset"), (-301, "Upset"), (-250, "Frustrated"), (-100, "Sarcastic"), (0, "Neutral"),
                            (100, "Friendly"), (200, "Close"), (400, "Infatuated")):
            self.assertEqual(e._band_for(score, None), band, score)
        for band, low, high in (("Neutral", -50, 50), ("Friendly", 50, 150), ("Close", 150, 300), ("Infatuated", 300, 500),
                                ("Sarcastic", -175, -50), ("Frustrated", -300, -175), ("Upset", -500, -300)):
            levels = [e.level_for(low + (high - low) * (i + 0.5) / LEVELS, band) for i in range(LEVELS)]
            self.assertEqual(levels, [1, 2, 3, 4, 5], band)
            self.assertEqual(e.level_for(low, band), 1)
            self.assertEqual(e.level_for(high - 0.01, band), 5)

    def test_score_goes_to_500_and_no_further(self):
        e, _ = engine()
        e.score = 499
        e.band = e._band_for(e.score, None)
        self.assertEqual((e.band, e.level), ("Infatuated", 5))
        self.assertEqual(e.max_score, 500)

    def test_level_is_published_and_describe_shows_it(self):
        e, settings = engine()
        e.score = 60
        e.band = "Friendly"
        e.refresh()
        self.assertEqual(settings.get("personality.mood_level_live"), e.level)
        self.assertIn("Friendly", e.describe())
        self.assertIn("/5", e.describe())

    def test_fixed_level_comes_from_the_dashboard_setting(self):
        settings = Settings(Path("nope.json")).load()
        settings.set("personality.mood_mode", "fixed")
        settings.set("personality.mood_level", 5)
        self.assertEqual(effective_level(settings), 5)
        settings.set("personality.mood_level", 99)
        self.assertEqual(effective_level(settings), 5)

    def test_it_takes_five_times_longer_to_max_out(self):
        e, _ = engine(scale=5)
        self.assertEqual(e._bounds()[6], 300)
        old, _ = engine(scale=1)
        self.assertEqual(old._bounds()[6], 60)


class LegacySaveTests(unittest.TestCase):
    def converted(self, old_score, scale=5):
        folder = tempfile.mkdtemp()
        path = Path(folder) / "mood.json"
        path.write_text(json.dumps({"score": old_score, "saved_at": 1000.0}))
        e, _ = engine(scale=scale, save=path)
        return e

    def test_a_maxed_old_mood_keeps_its_mood_and_starts_the_climb(self):
        e = self.converted(100)
        self.assertEqual(e.band, "Infatuated")
        self.assertLessEqual(e.level, 2)
        self.assertLess(e.score, 400)

    def test_every_old_band_stays_the_same_mood(self):
        for old, band in ((80, "Infatuated"), (45, "Close"), (20, "Friendly"), (0, "Neutral"), (-20, "Sarcastic"),
                          (-45, "Frustrated"), (-80, "Upset")):
            self.assertEqual(self.converted(old).band, band, old)

    def test_bad_moods_start_near_the_neutral_end(self):
        e = self.converted(-80)
        self.assertEqual(e.band, "Upset")
        self.assertGreaterEqual(e.level, 4)       # an old Upset restarts mildly, near the top of Upset

    def test_new_saves_are_not_converted_twice(self):
        folder = tempfile.mkdtemp()
        path = Path(folder) / "mood.json"
        e, _ = engine(scale=5, save=path)
        e.score = 123.0
        e.save()
        again, _ = engine(scale=5, save=path)
        self.assertAlmostEqual(again.score, 123.0, places=1)

    def test_scale_one_keeps_old_numbers(self):
        self.assertAlmostEqual(self.converted(37, scale=1).score, 37)


if __name__ == "__main__":
    unittest.main()


class ToneLineTests(unittest.TestCase):
    def test_every_mood_and_level_has_lines(self):
        from personality.dialogue import DialogueManager as Dialogue
        from core import paths
        d = Dialogue(paths.VOICEPACKS_DIR / "default") if hasattr(paths, "VOICEPACKS_DIR") else None
        if d is None:
            self.skipTest("no voicepack path")
        d.load()
        for mood in ("Infatuated", "Close", "Friendly", "Neutral", "Sarcastic", "Frustrated", "Upset"):
            for level in range(1, 6):
                self.assertGreaterEqual(len(d.lines.get("Tone_%s_L%d" % (mood, level), [])), 5, (mood, level))

    def test_flavour_uses_the_level(self):
        import random
        from personality.flavour import Flavour
        from personality.dialogue import DialogueManager as Dialogue
        from core import paths
        settings = Settings(Path("nope.json")).load()
        settings.set("personality.mood_mode", "fixed")
        settings.set("personality.mood", "Friendly")
        d = Dialogue(paths.VOICEPACKS_DIR / "default")
        d.load()
        f = Flavour(d, settings, rng=random.Random(1))
        for level in (1, 5):
            settings.set("personality.mood_level", level)
            heard = {f._tone("Friendly") for _ in range(40)}
            wanted = {l.text for l in d.lines["Tone_Friendly_L%d" % level]}
            self.assertTrue(heard <= wanted, level)

    def test_neutral_makes_more_remarks_and_warmer_levels_more_than_cold_ones(self):
        from personality.flavour import Flavour
        settings = Settings(Path("nope.json")).load()
        settings.set("personality.mood_mode", "fixed")
        f = Flavour(None, settings)
        settings.set("personality.mood_level", 5)
        from unittest import mock
        with mock.patch("personality.flavour.NEUTRAL_BOOST", 1.6):
            self.assertGreater(f.level_factor("Neutral"), 1.0)
        settings.set("personality.mood_level", 1)
        low = f.level_factor("Friendly")
        settings.set("personality.mood_level", 5)
        self.assertGreater(f.level_factor("Friendly"), low)
        settings.set("personality.mood_level", 1)
        cold = f.level_factor("Upset")
        settings.set("personality.mood_level", 5)
        self.assertLess(f.level_factor("Upset"), cold)
