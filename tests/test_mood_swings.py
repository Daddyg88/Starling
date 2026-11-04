import unittest
from pathlib import Path

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality import mood_engine
from personality.dialogue import DialogueManager
from personality.mood_engine import MoodEngine


class Ev:
    def __init__(self, name, data=None, priority="normal"):
        self.name, self.data, self.priority = name, data or {}, priority


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class SwingTests(unittest.TestCase):
    def make(self, mood_start=0.0):
        self.clock = Clock()
        self.spoken = []
        self.settings = Settings(Path("nope.json")).load()
        self.engine = MoodEngine(EventBus(), self.settings, persist=False, clock=self.clock, speak=self.spoken.append,
                                 dialogue=DialogueManager(paths.VOICEPACKS_DIR / "default").load())
        self.engine.score = mood_start * self.engine.scale
        self.engine.band = self.engine._band_for(self.engine.score, None)
        self.engine._publish_live()
        return self.engine

    def test_dying_makes_her_upset_for_five_minutes_then_she_forgives_and_returns(self):
        e = self.make(mood_start=20)                              # Friendly
        before = e.band
        self.assertEqual(before, "Friendly")
        e.on_event(Ev("Died", {"KillerName": "x"}))               # died in a fight: no score penalty
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")
        self.assertEqual(e.band, before)                          # the real mood is untouched
        self.clock.t += 4 * 60
        e.check_swing()
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")
        self.clock.t += 61
        self.assertTrue(e.check_swing())
        self.assertEqual(self.settings.get("personality.mood_live"), before)
        self.assertTrue(any("forgive" in t.lower() or "sulk" in t.lower() or "cross" in t.lower() or "upset" in t.lower()
                            for t in self.spoken), self.spoken)

    def test_unsold_data_is_lost_on_death_as_a_second_penalty(self):
        e = self.make(mood_start=20)
        for _ in range(30):
            e.on_event(Ev("Scan", {"BodyName": "x"}))
        score = e.score
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.assertLess(e.score, score)
        e.on_event(Ev("Died", {"KillerName": "x"}))               # nothing left to lose the second time
        again = e.score
        self.assertEqual(e._unsold, 0)

    def test_selling_data_first_means_nothing_to_lose(self):
        e = self.make(mood_start=20)
        for _ in range(30):
            e.on_event(Ev("Scan", {"BodyName": "x"}))
        e.on_event(Ev("SellExplorationData", {"TotalEarnings": 1000}))
        self.assertEqual(e._unsold, 0)
        score = e.score
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.assertEqual(e.score, score)

    def test_selling_at_a_loss_costs_points_and_a_profit_does_not(self):
        e = self.make(mood_start=20)
        score = e.score
        e.on_event(Ev("MarketSell", {"Count": 100, "TotalSale": 10000, "AvgPricePaid": 600}))       # lost 50000
        self.assertLess(e.score, score)
        score = e.score
        e.on_event(Ev("MarketSell", {"Count": 10, "TotalSale": 9000, "AvgPricePaid": 500}))
        self.assertEqual(e.score, score)

    def test_a_very_big_loss_also_makes_her_sarcastic_for_a_while(self):
        e = self.make(mood_start=20)
        e.on_event(Ev("MarketSell", {"Count": 100, "TotalSale": 0, "AvgPricePaid": 5000}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Sarcastic")

    def test_a_rebuy_costs_points(self):
        e = self.make(mood_start=20)
        score = e.score
        e.on_event(Ev("Resurrect", {"Option": "rebuy", "Cost": 20_000_000}))
        self.assertLess(e.score, score)

    def test_good_news_gives_a_happy_swing_that_ends_without_changing_the_score(self):
        e = self.make(mood_start=0)
        e.on_event(Ev("Bounty", {"TotalReward": 5_000_000}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Infatuated")
        self.clock.t += 181
        e.check_swing()
        self.assertNotEqual(self.settings.get("personality.mood_live"), "Infatuated")

    def test_a_worse_swing_is_not_replaced_by_a_milder_one(self):
        e = self.make()
        e.on_event(Ev("Died", {"KillerName": "x"}))
        e.on_event(Ev("MissionFailed", {}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")

    def test_the_rules_file_swings_and_lines_are_valid(self):
        swings = mood_engine.load_swings()
        self.assertGreaterEqual(len(swings), 6)
        known = set(DialogueManager(paths.VOICEPACKS_DIR / "default").load().lines)
        for s in swings:
            self.assertIn(s["forgive"], known)
        for key in ("React_DataLost", "React_Rebuy", "React_TradeLoss", "OnFootLastGrenade", "OnFootMedpack"):
            self.assertIn(key, known)

    def test_reset_clears_a_swing(self):
        e = self.make()
        e.on_event(Ev("Died", {"KillerName": "x"}))
        e.reset()
        self.assertFalse(e.swing_active())


if __name__ == "__main__":
    unittest.main()


class LoginTests(unittest.TestCase):
    def test_login_while_still_upset_says_so(self):
        from personality.greeter import LoginGreeter
        clock = Clock()
        settings = Settings(Path("nope.json")).load()
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        engine = MoodEngine(EventBus(), settings, persist=False, clock=clock, dialogue=dialogue)
        greeter = LoginGreeter(EventBus(), None, dialogue, settings, mood=engine)
        before = greeter.compose({"Ship": "python"}, None)
        engine.on_event(Ev("Died", {"KillerName": "x"}))
        text = greeter.compose({"Ship": "python"}, None)
        self.assertIn("dying", text.lower())
        clock.t += 6 * 60
        engine.check_swing()
        self.assertNotIn("dying", greeter.compose({"Ship": "python"}, None).lower())

    def test_every_swing_has_a_still_line(self):
        known = set(DialogueManager(paths.VOICEPACKS_DIR / "default").load().lines)
        for s in mood_engine.load_swings():
            self.assertIn(s["still"], known)


class ExoMoodTests(SwingTests):
    def test_big_exo_sale_is_a_lasting_full_amount_gain(self):
        e = self.make(mood_start=5)
        score = e.score
        e.on_event(Ev("SellOrganicData", {"TotalValue": 500_000_000}))
        self.assertAlmostEqual(e.score - score, 34 * e.scale, delta=1.0)    # the whole tier, not cut by the hourly cap
        self.assertFalse(e.swing_active())                                   # no short-lived swing that fades away
        score = e.score
        e.on_event(Ev("SellOrganicData", {"TotalValue": 500_000_000}))       # and no soft cap on a second one
        self.assertAlmostEqual(e.score - score, 34 * e.scale, delta=1.0)

    def test_every_exo_tier_is_higher_than_before(self):
        rule = next(r for r in mood_engine.load_rules()[1] if r["id"] == "sell_exo")
        old = [[100000, 1], [1000000, 2], [10000000, 3], [100000000, 4]]
        for minimum, points in old:
            mine = max(p for m, p in rule["tiers"] if m <= minimum)
            self.assertGreaterEqual(mine, points)
        self.assertGreater(max(p for _m, p in rule["tiers"]), 30)

    def test_dying_with_lots_of_exo_is_very_upset_then_back_to_where_she_was(self):
        e = self.make(mood_start=20)
        carried = [30_000_000]
        e.exo_provider = lambda: carried[0]
        e.on_event(Ev("Scan", {"BodyName": "x"}))                  # she notices what you carry
        score = e.score
        carried[0] = 0                                             # the tracker empties on death
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")
        self.assertEqual(e._shown_level(), 1)                      # very upset
        self.assertEqual(e.score, score)                           # nothing permanent lost
        self.clock.t += 9 * 60
        e.check_swing()
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")   # longer than an ordinary death
        self.clock.t += 61
        self.assertTrue(e.check_swing())
        self.assertEqual(self.settings.get("personality.mood_live"), "Friendly")
        self.assertEqual(e.score, score)
        self.assertTrue(any("exobiology" in t.lower() or "samples" in t.lower() or "data" in t.lower() for t in self.spoken), self.spoken)

    def test_dying_with_little_exo_is_the_ordinary_death(self):
        e = self.make(mood_start=20)
        e.exo_provider = lambda: 1_000_000
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.clock.t += 5 * 60 + 1
        self.assertTrue(e.check_swing())                           # the ordinary five minutes
