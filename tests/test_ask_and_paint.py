"""Tests: yes/no questions, facts, valuable-planet and life prompts, paintwork mood, settings kept."""

import json
import tempfile
import unittest
from pathlib import Path

from core import paths
from core.event_bus import EventBus
from personality.ask import AskManager, DECLINES_BEFORE_PENALTY
from personality.answers import classify, wants_a_fact
from personality.dialogue import DialogueManager
from personality.facts import FactBook
from personality.mood_engine import MoodEngine
from tests.test_commands import FakeSpeech
from tests.test_phase6b import make_settings


def dialogue():
    return DialogueManager(paths.VOICEPACKS_DIR / "default").load()


class FakeTimer:
    def __init__(self, seconds, function):
        self.seconds, self.function, self.cancelled, self.started = seconds, function, False, False

    def start(self): self.started = True
    def cancel(self): self.cancelled = True
    def fire(self):
        if not self.cancelled:
            self.cancelled = True          # a timer only goes off once
            self.function()


class Rig:
    """An AskManager with a fake clock, fake timers, a fake mouth and a real mood engine listening."""

    def __init__(self, **values):
        values.setdefault("facts__frequency", "often")
        values.setdefault("personality__mood_mode", "fixed")
        values.setdefault("personality__mood", "Neutral")
        self.settings = make_settings(**values)
        self.bus, self.speech = EventBus(), FakeSpeech()
        self.now = [1000.0]
        self.timers = []
        self.listening = True
        self.state = type("S", (), {"status_flags": 0})()
        d = dialogue()
        self.facts = FactBook(d, save_path=Path(tempfile.gettempdir()) / "facts_test.json", persist=False)
        self.ask = AskManager(self.bus, self.speech, d, self.settings, self.facts, state_provider=lambda: self.state,
                              listening_provider=lambda: self.listening, clock=lambda: self.now[0],
                              rng=__import__("random").Random(1), timer_factory=self._timer)
        self.ask.attach()
        self.mood = MoodEngine(self.bus, self.settings, rules_path=paths.CONFIG_DIR / "mood_rules.json", persist=False,
                               dialogue=d, clock=lambda: self.now[0])
        self.mood.attach()
        self.start = self.mood.score

    def _timer(self, seconds, function):
        t = FakeTimer(seconds, function)
        self.timers.append(t)
        return t

    def fire_timers(self):
        for t in list(self.timers):
            t.fire()

    def spoken_kinds(self):
        return [s.get("event_name") for s in self.speech.said]

    def arrive(self):
        self.bus.publish("FSDJump", {"StarSystem": "Sol"}, "normal")
        self.fire_timers()

    def finish_question(self):
        self.bus.publish("speech.finished", {"event": "ask.question", "text": "x"}, "low")

    def say(self, text, wake=True):
        return self.ask.handle_heard(text, wake, text if wake else "", False)

    def expire_answer_window(self):
        self.timers[-1].fire()


class AnswerTests(unittest.TestCase):
    def test_many_ways_to_say_yes_and_no(self):
        for t in ("yes", "yeah", "yep please", "sure thing", "go on", "go ahead", "why not", "of course", "okay", "tell me", "fire away"):
            self.assertEqual(classify(t), "yes", t)
        for t in ("no", "nope", "nah", "no thanks", "not now", "maybe later", "not really", "I'm good", "negative", "another time"):
            self.assertEqual(classify(t), "no", t)

    def test_commands_are_not_answers(self):
        for t in ("lower the landing gear", "go to supercruise", "open the galaxy map", "engage jump"):
            self.assertIsNone(classify(t), t)

    def test_asking_for_a_fact(self):
        for t in ("tell me a fact", "give me a fun fact", "got any trivia", "tell me something interesting"):
            self.assertTrue(wants_a_fact(t), t)
        self.assertFalse(wants_a_fact("open the galaxy map"))


class FactTests(unittest.TestCase):
    def test_there_are_plenty_of_facts(self):
        d = dialogue()
        total = sum(len(d.lines.get(k, [])) for k in ("Fact_Elite", "Fact_Real", "Fact_Planets"))
        self.assertGreaterEqual(total, 200)
        self.assertLessEqual(total, 320)
        for k in ("Fact_Elite", "Fact_Real", "Fact_Planets"):
            for line in d.lines[k]:
                self.assertLess(len(line.text), 260, line.text)
                self.assertNotIn("{", line.text)

    def test_no_fact_repeats_until_all_are_told(self):
        d = dialogue()
        book = FactBook(d, persist=False)
        n = book.count("planets")
        told = [book.next("planets") for _ in range(n)]
        self.assertEqual(len(set(told)), n)

    def test_the_fact_book_is_remembered_between_runs(self):
        d = dialogue()
        path = Path(tempfile.mkdtemp()) / "facts_seen.json"
        first = FactBook(d, save_path=path).next("elite")
        again = FactBook(d, save_path=path)
        self.assertIn(first, [l.text for l in d.lines["Fact_Elite"]])
        self.assertEqual(len(again.seen), 1)

    def test_no_bloody_in_facts_and_questions(self):
        for name in ("facts.json", "ask.json"):
            self.assertNotIn("bloody", (paths.VOICEPACKS_DIR / "default" / name).read_text(encoding="utf-8").lower())


class FactChatTests(unittest.TestCase):
    def test_arriving_makes_her_offer_a_fact_then_yes_tells_it(self):
        r = Rig()
        r.arrive()
        self.assertEqual(r.spoken_kinds(), ["ask.question"])
        r.finish_question()
        before = r.mood.score
        self.assertTrue(r.say("Starling yes please"))
        self.assertIn("ask.fact", r.spoken_kinds())
        self.assertGreater(r.mood.score, before)
        fact_text = r.speech.said[-1]["text"]
        self.assertIn("||", fact_text)

    def test_yes_without_the_wake_word_also_works_during_a_question(self):
        r = Rig()
        r.arrive(); r.finish_question()
        self.assertTrue(r.say("yeah go on", wake=False))

    def test_when_nobody_is_asked_nothing_is_taken_as_an_answer(self):
        r = Rig()
        self.assertFalse(r.say("yes"))

    def test_no_means_no_penalty_at_first(self):
        r = Rig()
        r.arrive(); r.finish_question()
        before = r.mood.score
        r.say("no thanks")
        self.assertEqual(r.mood.score, before)

    def test_turning_her_down_too_often_costs_mood(self):
        r = Rig()
        before = r.mood.score
        for _ in range(DECLINES_BEFORE_PENALTY):
            r.now[0] += 100000
            r._last = None
            r.ask._last_fact_offer = None
            r.arrive(); r.finish_question()
            r.say("no")
        self.assertLess(r.mood.score, before)

    def test_ignoring_her_costs_a_little_and_counts_as_no(self):
        r = Rig()
        r.arrive(); r.finish_question()
        before = r.mood.score
        r.expire_answer_window()
        self.assertLess(r.mood.score, before)
        self.assertEqual(r.ask.declines, 1)

    def test_penalties_have_a_soft_cap(self):
        r = Rig()
        scores = []
        for _ in range(5):
            r.now[0] += 100
            r.ask._last_fact_offer = None
            r.ask._last_asked = None
            r.arrive(); r.finish_question()
            r.expire_answer_window()
            scores.append(r.mood.score)
        drops = [a - b for a, b in zip(scores, scores[1:])]
        self.assertTrue(all(later <= earlier + 1e-9 for earlier, later in zip(drops, drops[1:])), drops)

    def test_she_does_not_ask_when_she_cannot_hear_you(self):
        r = Rig()
        r.listening = False
        r.arrive()
        self.assertEqual(r.spoken_kinds(), [])

    def test_frequency_never_means_never(self):
        r = Rig(facts__frequency="off")
        r.arrive()
        self.assertEqual(r.spoken_kinds(), [])

    def test_not_too_often(self):
        r = Rig(facts__frequency="rarely")
        r.arrive(); r.finish_question(); r.say("no")
        r.now[0] += 300
        r.arrive()
        self.assertEqual(r.spoken_kinds().count("ask.question"), 1)

    def test_a_safety_warning_cancels_the_question_without_penalty(self):
        r = Rig()
        r.arrive(); r.finish_question()
        before = r.mood.score
        r.bus.publish("HullDamage", {"Percent": 20}, "critical")
        r.timers[-1].fire()
        self.assertEqual(r.mood.score, before)
        self.assertIsNone(r.ask.pending)

    def test_never_while_weapons_are_out(self):
        r = Rig()
        r.state.status_flags = 1 << 6
        r.arrive()
        self.assertEqual(r.spoken_kinds(), [])

    def test_tell_me_a_fact_works_any_time(self):
        r = Rig()
        self.assertTrue(r.say("Starling tell me a fun fact"))
        self.assertIn("ask.fact", r.spoken_kinds())

    def test_next_jump_cancels_the_pending_offer(self):
        r = Rig()
        r.bus.publish("FSDJump", {}, "normal")
        r.bus.publish("StartJump", {}, "normal")
        r.fire_timers()
        self.assertEqual(r.spoken_kinds(), [])


class PlanetPromptTests(unittest.TestCase):
    EARTHLIKE = {"BodyName": "Sol 3", "PlanetClass": "Earthlike body"}

    def test_valuable_world_asks_and_yes_is_rewarded(self):
        r = Rig()
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        self.assertEqual(r.spoken_kinds(), ["ask.question"])
        r.finish_question()
        before = r.mood.score
        r.say("yes")
        self.assertGreater(r.mood.score, before)

    def test_no_to_a_scan_is_free(self):
        r = Rig()
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        r.finish_question()
        before = r.mood.score
        r.say("no")
        self.assertEqual(r.mood.score, before)

    def test_ignoring_a_scan_question_costs_mood(self):
        r = Rig()
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        r.finish_question()
        before = r.mood.score
        r.expire_answer_window()
        self.assertLess(r.mood.score, before)

    def test_ordinary_worlds_and_mapped_worlds_are_not_asked_about(self):
        r = Rig()
        r.bus.publish("Scan", {"BodyName": "x", "PlanetClass": "Rocky body"}, "low")
        r.bus.publish("Scan", dict(self.EARTHLIKE, WasMapped=True, BodyName="y"), "low")
        self.assertEqual(r.spoken_kinds(), [])

    def test_each_body_is_asked_about_once(self):
        r = Rig()
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        r.finish_question(); r.say("no")
        r.now[0] += 1000
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        self.assertEqual(r.spoken_kinds().count("ask.question"), 1)

    def test_life_is_only_wondered_about_aloud_with_no_answer_or_mood_effect(self):
        r = Rig()
        before = r.mood.score
        r.bus.publish("FSSBodySignals", {"BodyName": "A 1", "Biological": 3}, "normal")
        self.assertEqual(r.spoken_kinds(), ["ask.bio"])
        self.assertIsNone(r.ask.pending)                     # nothing is waiting for a yes or no
        self.assertFalse(r.say("yes"))                       # so "yes" is not taken as an answer
        r.now[0] += 500
        r.fire_timers()
        self.assertEqual(r.mood.score, before)               # ignoring it changes nothing
        self.assertTrue(r.speech.said[0]["text"].endswith("?"))

    def test_life_is_wondered_about_once_per_planet_and_even_without_listening(self):
        r = Rig()
        r.listening = False
        r.bus.publish("FSSBodySignals", {"BodyName": "A 1", "Biological": 3}, "normal")
        r.bus.publish("SAASignalsFound", {"BodyName": "A 1", "Biological": 3}, "normal")
        self.assertEqual(r.spoken_kinds(), ["ask.bio"])

    def test_no_bio_answer_lines_or_mood_rules_remain(self):
        d = dialogue()
        self.assertNotIn("Ask_BioYes", d.lines)
        rules = (paths.CONFIG_DIR / "mood_rules.json").read_text(encoding="utf-8")
        self.assertNotIn("bio_yes", rules)
        self.assertNotIn("bio_ignored", rules)

    def test_prompts_can_be_switched_off(self):
        r = Rig(ask__scan_prompts=False, ask__bio_prompts=False)
        r.bus.publish("Scan", dict(self.EARTHLIKE), "low")
        r.bus.publish("FSSBodySignals", {"BodyName": "A 1", "Biological": 2}, "normal")
        self.assertEqual(r.spoken_kinds(), [])

    def test_the_answer_is_not_also_run_as_a_voice_command(self):
        from stt.listener import Listener
        from tests.test_stt import FakeSTT, FakeMic
        r = Rig()
        r.arrive(); r.finish_question()
        heard = []
        r.bus.subscribe("voice.heard", lambda e: heard.append(e))
        listener = Listener(r.bus, FakeSTT(), r.settings, lambda: FakeMic([]))
        listener.interceptor = r.ask.handle_heard
        listener.handle_text("Starling, yes please")
        self.assertEqual(heard, [])


class HumourTests(unittest.TestCase):
    def flavour(self, mood, **values):
        from personality.flavour import Flavour
        s = make_settings(personality__mood_mode="fixed", personality__mood=mood, personality__remarks="often", **values)
        d = dialogue()
        return Flavour(d, s, lambda: 0, clock=lambda: 0.0), d

    def texts(self, d, key):
        return {l.text for l in d.lines.get(key, [])}

    def test_dark_humour_exists_for_every_mood(self):
        d = dialogue()
        self.assertGreaterEqual(len(d.lines["Remark_Dark"]), 25)
        for mood in ("Neutral", "Friendly", "Close", "Sarcastic", "Frustrated"):
            f, d = self.flavour(mood)
            self.assertTrue(f._dark_remark(mood), mood)

    def test_dark_humour_shows_up_in_every_mood_and_can_be_switched_off(self):
        for mood in ("Neutral", "Friendly", "Close", "Sarcastic", "Frustrated"):
            f, d = self.flavour(mood)
            dark = set()
            for key in [k for k in d.lines if k.startswith("Remark_Dark")]:
                dark |= self.texts(d, key)
            got = set()
            for _ in range(400):
                f._last_remark = None
                got.add(f.apply("Docked.", "normal").split("||")[-1].strip())
            self.assertTrue(got & dark, mood)
            f2, _ = self.flavour(mood, personality__dark_humour=False)
            for _ in range(200):
                f2._last_remark = None
                self.assertFalse({f2.apply("Docked.", "normal").split("||")[-1].strip()} & dark, mood)

    def test_dark_humour_never_touches_safety_warnings(self):
        f, d = self.flavour("Sarcastic")
        for _ in range(100):
            self.assertEqual(f.apply("Hull critical.", "critical"), "Hull critical.")

    def test_bad_moods_get_rude_innuendo_only_with_the_switch_on(self):
        for mood in ("Sarcastic", "Frustrated"):
            f, d = self.flavour(mood, personality__innuendo=True, personality__dark_humour=False)
            grumpy = self.texts(d, "Remark_Innuendo_Grumpy")
            self.assertGreaterEqual(len(grumpy), 20)
            happy = self.texts(d, "Remark_Innuendo")
            got = set()
            for _ in range(500):
                f._last_remark = None
                got.add(f.apply("Docked.", "normal").split("||")[-1].strip())
            self.assertTrue(got & grumpy, mood)
            self.assertFalse(got & happy, mood)
            off, _ = self.flavour(mood, personality__innuendo=False, personality__dark_humour=False)
            for _ in range(200):
                off._last_remark = None
                self.assertFalse({off.apply("Docked.", "normal").split("||")[-1].strip()} & grumpy, mood)

    def test_the_strong_rude_lines_need_strong_language(self):
        d = dialogue()
        strong = {l.text for l in d.lines["Remark_Innuendo_Grumpy"] if l.mature}
        self.assertTrue(strong)
        f, _ = self.flavour("Frustrated", personality__innuendo=True, speech__allow_mature=False)
        for _ in range(300):
            f._last_remark = None
            self.assertNotIn(f.apply("Docked.", "normal").split("||")[-1].strip(), strong)

    def test_the_login_greeting_never_uses_happy_innuendo_in_a_bad_mood(self):
        from personality.greeter import LoginGreeter
        self.assertIn('"Sarcastic", "Frustrated"', open(__import__("inspect").getsourcefile(LoginGreeter), encoding="utf-8").read())

    def test_no_taste_problems_in_the_dark_lines(self):
        d = dialogue()
        for key in [k for k in d.lines if k.startswith("Remark_Dark")]:
            for line in d.lines[key]:
                low = line.text.lower()
                self.assertNotIn("suicide", low)
                self.assertNotIn("kill yourself", low)


class PaintTests(unittest.TestCase):
    def build(self):
        self.now = [1000.0]
        self.settings = make_settings(personality__mood_mode="auto")
        self.bus = EventBus()
        self.mood = MoodEngine(self.bus, self.settings, rules_path=paths.CONFIG_DIR / "mood_rules.json", persist=False,
                               clock=lambda: self.now[0])
        self.mood.attach()
        self.mood.options["paint_worn_after_jumps"] = 5
        self.mood.options["time_together_minutes"] = 10 ** 6      # keep other mood rules out of these tests
        self.mood.options["calm_minutes_per_point"] = 10 ** 9
        return self.mood

    def jump(self, n=1):
        for _ in range(n):
            self.bus.publish("FSDJump", {"StarSystem": "x"}, "normal")

    def test_paint_wears_out_after_enough_jumps_and_drains_mood(self):
        m = self.build()
        self.jump(3)
        self.assertFalse(m.paint_worn())
        self.jump(3)
        self.assertTrue(m.paint_worn())
        start = m.score
        for _ in range(12):
            self.now[0] += 290
            self.bus.publish("FuelScoop", {}, "low")        # keeps "actively playing" true
        self.assertLess(m.score, start)
        self.assertGreater(m.paint_debt, 0)

    def test_repainting_gives_back_exactly_what_was_lost(self):
        m = self.build()
        self.jump(6)
        start = m.score
        for _ in range(30):
            self.now[0] += 290
            self.bus.publish("FuelScoop", {}, "low")
        lost = start - m.score
        self.assertGreater(lost, 0.5)
        m.options["calm_minutes_per_point"] = 10 ** 9            # ignore the slow drift back to neutral in this test
        low = m.score
        self.bus.publish("Repair", {"Item": "paint"}, "low")
        self.assertAlmostEqual(m.score - low, lost, places=1)
        self.assertFalse(m.paint_worn())
        self.assertEqual(m.paint_debt, 0)

    def test_repair_all_does_not_fix_paint(self):
        m = self.build()
        self.jump(6)
        self.bus.publish("RepairAll", {"Cost": 10}, "low")
        self.assertTrue(m.paint_worn())
        self.bus.publish("Repair", {"Item": "hull"}, "low")
        self.assertTrue(m.paint_worn())

    def test_a_floor_stops_it_getting_silly(self):
        m = self.build()
        self.jump(6)
        for _ in range(400):
            self.now[0] += 290
            self.bus.publish("FuelScoop", {}, "low")
        self.assertGreaterEqual(m.score, m.options["paint_floor"] - 1)

    def test_wear_and_mood_are_saved_between_runs(self):
        folder = Path(tempfile.mkdtemp())
        path = folder / "mood.json"
        settings = make_settings()
        a = MoodEngine(EventBus(), settings, rules_path=paths.CONFIG_DIR / "mood_rules.json", save_path=path, persist=True)
        a.paint_jumps, a.paint_debt, a.score = 42, 1.5, 12.0
        a.save()
        a.save()
        self.assertTrue((folder / "mood.json.bak").exists())
        b = MoodEngine(EventBus(), settings, rules_path=paths.CONFIG_DIR / "mood_rules.json", save_path=path, persist=True)
        self.assertEqual((b.paint_jumps, b.paint_debt), (42, 1.5))
        self.assertGreater(b.score, 0)


class ZipHygieneTests(unittest.TestCase):
    def test_the_dashboard_has_a_chat_box(self):
        from ui.settings_model import build_pages
        page = next(p for p in build_pages() if p.id == "chat")
        keys = {f.key for f in page.fields}
        self.assertTrue({"facts.frequency", "facts.topics", "ask.scan_prompts", "ask.bio_prompts"} <= keys)
        freq = next(f for f in page.fields if f.key == "facts.frequency")
        self.assertEqual([v for _l, v in freq.choices], ["off", "rarely", "sometimes", "often", "very_often"])

    def test_defaults_exist_for_the_new_settings(self):
        from core.settings import DEFAULTS
        self.assertEqual(DEFAULTS["facts"]["frequency"], "sometimes")
        self.assertTrue(DEFAULTS["ask"]["scan_prompts"])


if __name__ == "__main__":
    unittest.main()
