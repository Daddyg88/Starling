"""Random mood (a new mood every 20 minutes) and keeping your points safe when she is not in Automatic (0.96.0)."""
import random
import unittest

from personality.mood_engine import BANDS, LEVELS, effective_level, effective_mood, mood_mode
from tests.test_mood import MoodBase


class Modes(MoodBase):
    def go(self, mode):
        self.settings.set("personality.mood_mode", mode)

    def test_random_mode_shows_the_random_mood_and_level(self):
        self.go("random")
        self.settings.set("personality.mood_random", "Sarcastic")
        self.settings.set("personality.mood_random_level", 4)
        self.assertEqual(effective_mood(self.settings), "Sarcastic")
        self.assertEqual(effective_level(self.settings), 4)

    def test_a_broken_random_mood_falls_back_to_friendly(self):
        self.go("random")
        self.settings.set("personality.mood_random", "Hungry")
        self.assertEqual(effective_mood(self.settings), "Friendly")
        self.go("nonsense")
        self.assertEqual(mood_mode(self.settings), "auto")

    def test_nothing_changes_unless_the_mode_is_random(self):
        for mode in ("auto", "fixed"):
            self.go(mode)
            self.assertFalse(self.engine.check_random())

    def test_random_picks_now_then_every_20_minutes(self):
        self.go("random")
        self.assertTrue(self.engine.check_random())
        first = effective_mood(self.settings)
        self.assertIn(first, BANDS)
        self.assertIn(effective_level(self.settings), range(1, LEVELS + 1))
        self.clock.wait(19)
        self.assertFalse(self.engine.check_random())
        self.assertEqual(effective_mood(self.settings), first)
        self.clock.wait(1.1)
        self.assertTrue(self.engine.check_random())
        self.assertNotEqual(effective_mood(self.settings), first)         # never the same mood twice in a row

    def test_the_interval_can_be_changed(self):
        self.go("random")
        self.settings.set("personality.mood_random_minutes", 10)
        self.engine.check_random()
        self.clock.wait(9)
        self.assertFalse(self.engine.check_random())
        self.clock.wait(1.5)
        self.assertTrue(self.engine.check_random())

    def test_every_mood_turns_up_and_none_twice_running(self):
        self.go("random")
        self.engine.rng = random.Random(7)
        seen, last = set(), None
        for _ in range(200):
            self.clock.wait(21)
            self.assertTrue(self.engine.check_random())
            mood = effective_mood(self.settings)
            self.assertNotEqual(mood, last)
            seen.add(mood)
            last = mood
        self.assertEqual(seen, set(BANDS))

    def test_going_back_to_automatic_and_into_random_again_picks_fresh(self):
        self.go("random")
        self.engine.check_random()
        self.go("auto")
        self.assertFalse(self.engine.check_random())
        self.go("random")
        self.assertTrue(self.engine.check_random())


class KeepingPoints(MoodBase):
    def earn(self):
        self.engine.score = 45.0                          # well up in Close
        self.engine.refresh()
        self.assertEqual(effective_mood(self.settings), "Close")

    def play_a_while(self):
        self.engine._last_event = self.clock.t
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.send("Died")
        self.clock.wait(40)
        self.engine._last_event = self.clock.t
        self.engine.refresh()

    def test_random_mode_does_not_touch_the_score(self):
        self.earn()
        before = self.engine.score
        self.settings.set("personality.mood_mode", "random")
        self.play_a_while()
        self.assertEqual(self.engine.score, before)

    def test_fixed_mode_does_not_touch_the_score_either(self):
        self.earn()
        before = self.engine.score
        self.settings.set("personality.mood_mode", "fixed")
        self.play_a_while()
        self.assertEqual(self.engine.score, before)

    def test_switching_back_to_automatic_gives_the_same_mood_and_points(self):
        self.earn()
        before = self.engine.score
        self.settings.set("personality.mood_mode", "random")
        self.play_a_while()
        self.settings.set("personality.mood_mode", "auto")
        self.engine.refresh()
        self.assertEqual(self.engine.score, before)
        self.assertEqual(effective_mood(self.settings), "Close")

    def test_the_time_spent_in_random_is_not_charged_when_she_comes_back(self):
        self.earn()
        before = self.engine.score
        self.settings.set("personality.mood_mode", "random")
        self.clock.wait(120)
        self.engine._last_event = self.clock.t
        self.engine.refresh()
        self.settings.set("personality.mood_mode", "auto")
        self.engine.refresh()
        self.assertEqual(self.engine.score, before)

    def test_automatic_still_moves_the_score(self):
        self.earn()
        before = self.engine.score
        self.play_a_while()
        self.assertLess(self.engine.score, before)

    def test_with_the_switch_off_the_score_keeps_following_the_game(self):
        self.earn()
        before = self.engine.score
        self.settings.set("personality.mood_mode", "fixed")
        self.settings.set("personality.keep_points", False)
        self.play_a_while()
        self.assertLess(self.engine.score, before)


class Dashboard(unittest.TestCase):
    def test_red_alert_lives_inside_combat(self):
        from ui.settings_model import SECTION_OF, build_pages
        self.assertEqual(SECTION_OF["redalert"], "combat")
        pages = build_pages()
        self.assertNotIn("redalert", [p.id for p in pages if not p.parent])
        red = [p for p in pages if p.id == "redalert"][0]
        self.assertEqual(red.parent, "combat")
        self.assertIn("red_alert.minutes", [f.key for f in red.fields])

    def test_the_new_mood_settings_are_on_the_personality_page(self):
        from ui.settings_model import MOOD_MODES, build_pages
        keys = [f.key for p in build_pages() for f in p.fields]
        for key in ("personality.mood_random_minutes", "personality.keep_points", "personality.mood_mode"):
            self.assertIn(key, keys)
        self.assertIn("random", [value for _label, value in MOOD_MODES])


if __name__ == "__main__":
    unittest.main()
