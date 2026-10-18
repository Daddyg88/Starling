"""Phase 6b tests: no double announcements, "engage jump", the Neutral mood, swearing in every mood, innuendo."""

import re
import tempfile
import unittest
from pathlib import Path

from control import binds
from control.binds import Keystroke
from control.echo import Echo
from control.runner import CommandRunner
from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from journal.game_state import GameState
from personality.dialogue import DialogueManager
from personality.flavour import Flavour
from personality.speaker import EventSpeaker
from tests.test_commands import FakeBook, FakeSender, FakeSpeech
from tests.test_flavour import Rng

MOODS = ("Neutral", "Friendly", "Close", "Sarcastic", "Frustrated")


def make_settings(**values):
    s = Settings(Path(tempfile.gettempdir()) / "nope_phase6b.json").load()
    for k, v in values.items():
        s.set(k.replace("__", "."), v)
    return s


def dialogue():
    return DialogueManager(paths.VOICEPACKS_DIR / "default").load()


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class EchoTests(unittest.TestCase):
    def test_an_event_she_caused_is_swallowed_once_then_expires(self):
        clock = Clock()
        echo = Echo(clock=clock)
        event = type("E", (), {"name": "GalaxyMapOpened", "priority": "low"})()
        self.assertFalse(echo.consume(event))             # nothing expected yet
        echo.expect(["GalaxyMapOpened"])
        self.assertTrue(echo.consume(event))
        self.assertFalse(echo.consume(event))             # only once
        echo.expect(["GalaxyMapOpened"])
        clock.t += 30
        self.assertFalse(echo.consume(event))             # too late: probably a different opening

    def test_warnings_are_never_swallowed(self):
        echo = Echo()
        echo.expect(["LowFuel"])
        self.assertFalse(echo.consume(type("E", (), {"name": "LowFuel", "priority": "critical"})()))


class NoDoubleSpeechTests(unittest.TestCase):
    def build(self):
        bus, speech, echo = EventBus(), FakeSpeech(), Echo()
        settings = make_settings()
        d = dialogue()
        speaker = EventSpeaker(bus, speech, d, settings, echo=echo)
        speaker.attach()
        book = FakeBook({"LandingGearToggle": (Keystroke("Key_L"), ""), "GalaxyMapOpen": (Keystroke("Key_M"), "")})
        runner = CommandRunner(bus, speech, d, settings, book=book, sender=FakeSender(), echo=echo, sleep=lambda s: None)
        return bus, speech, runner

    def test_open_galaxy_map_is_said_once_not_twice(self):
        bus, speech, runner = self.build()
        runner.run_text("open the galaxy map")
        self.assertEqual(len(speech.said), 1)                      # her confirmation
        bus.publish("GalaxyMapOpened", {"summary": "Opened the galaxy map"}, "low")   # the game's echo
        self.assertEqual(len(speech.said), 1)

    def test_the_same_event_from_you_pressing_the_key_yourself_is_still_announced(self):
        bus, speech, runner = self.build()
        bus.publish("LandingGearDown", {"summary": "Landing gear down"}, "normal")
        self.assertEqual(len(speech.said), 1)

    def test_if_nothing_was_pressed_nothing_is_swallowed(self):
        bus, speech, runner = self.build()
        runner.state_provider = lambda: type("S", (), {"status_seen": True, "status_flags": 1 << 2, "system": None})()
        runner.run_text("lower the landing gear")                  # already down: she only says so
        said = len(speech.said)
        bus.publish("LandingGearDown", {"summary": "Landing gear down"}, "normal")
        self.assertEqual(len(speech.said), said + 1)

    def test_every_command_that_changes_the_cockpit_names_its_echo(self):
        from control.catalog import CATALOG
        for cid in ("galaxy_map", "system_map", "gear", "weapons", "scoop", "lights", "night_vision", "silent_running",
                    "flight_assist", "hud_mode", "supercruise", "hyperspace"):
            command = next(c for c in CATALOG if c.id == cid)
            self.assertTrue(command.echo, cid)


class EngageJumpTests(unittest.TestCase):
    def build(self):
        book = FakeBook({"Supercruise": (Keystroke("Key_C"), ""), "Hyperspace": (Keystroke("Key_J"), "")})
        self.sender, self.speech = FakeSender(), FakeSpeech()
        return CommandRunner(EventBus(), self.speech, dialogue(), make_settings(), book=book, sender=self.sender,
                             state_provider=lambda: GameState(), sleep=lambda s: None)

    def test_engage_jump_is_the_hyperspace_jump_only(self):
        r = self.build()
        r.run_text("engage jump")
        self.assertEqual(self.sender.pressed, [Keystroke("Key_J")])

    def test_supercruise_stays_separate(self):
        r = self.build()
        r.run_text("engage supercruise")
        self.assertEqual(self.sender.pressed, [Keystroke("Key_C")])

    def test_many_ways_to_say_it(self):
        r = self.build()
        for text in ("engage jump", "jump", "engage the jump", "initiate the jump", "make the jump", "start the jump",
                     "jump to hyperspace", "engage hyperspace"):
            self.assertEqual(r.matcher.match(text).command.id, "hyperspace", text)

    def test_engage_supercruise_is_not_hyperspace(self):
        r = self.build()
        self.assertEqual(r.matcher.match("engage supercruise").command.id, "supercruise")


class SettingsKeptTests(unittest.TestCase):
    def test_saving_keeps_a_backup_of_the_previous_file(self):
        import tempfile, pathlib
        from core.settings import Settings
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "settings.json"
            s = Settings(path)
            s.set("speech.volume", 0.5); s.save()
            s.set("speech.volume", 0.7); s.save()
            self.assertTrue((pathlib.Path(d) / "settings.json.bak").exists())


class NeutralMoodTests(unittest.TestCase):
    def flavour(self, mood, mature=False, roll=0.0, **values):
        s = make_settings(personality__mood_mode="fixed", personality__mood=mood, speech__allow_mature=mature,
                          personality__remarks="often", personality__dark_humour=False, **values)
        d = dialogue()
        return Flavour(d, s, lambda: 0, rng=Rng(roll), clock=lambda: 0.0), d

    def test_neutral_is_in_the_dashboard_choices(self):
        from ui.settings_model import MOODS
        self.assertIn("Neutral", [value for _label, value in MOODS])
        self.assertEqual(len(MOODS), 5)

    def test_neutral_has_calm_remarks_and_pet_names(self):
        f, d = self.flavour("Neutral")
        calm = {l.text for l in d.lines["Remark_Neutral"] if not l.mature}
        out = f.apply("Docked, Commander.", "normal")
        self.assertIn(out.split("||")[-1].strip(), calm)
        self.assertNotIn("Commander", out.split("||")[0])
        self.assertIn(out.split("||")[0].split(",")[1].strip(" ."), {l.text for l in d.lines["PetName_Neutral"]})

    def test_neutral_has_lines_for_everything_the_other_moods_have(self):
        d = dialogue()
        for key in ("Login_Open_Neutral", "Login_Mood_Neutral", "Login_Ship_Neutral", "MoodShift_Neutral", "WakeHeard_Neutral",
                    "CommandDone_Neutral", "CommandAlready_Neutral", "CommandUnbound_Neutral", "CommandUnknown_Neutral",
                    "React_GoodSale_Neutral", "React_Murder_Neutral", "React_Slaves_Neutral", "Docked_Neutral", "LandingGearDown_Neutral"):
            self.assertTrue(d.lines.get(key), key)

    def test_dialogue_picks_up_neutral_lines_for_the_neutral_mood(self):
        d = dialogue()
        plain = {l.text for l in d.lines["Docked_Neutral"] if not l.mature}
        got = {d.pick("Docked", "Neutral", False, False).text for _ in range(60)}
        self.assertTrue(got & plain)
        self.assertFalse(any(d.pick("Docked", "Neutral", False, False).mature for _ in range(60)))


class SwearingInEveryMoodTests(unittest.TestCase):
    EVENTS = ("Docked", "FSDJump", "LandingGearDown", "MissionCompleted", "MarketSell", "Touchdown", "Bounty", "RouteComplete")

    def test_with_strong_language_on_every_mood_can_swear_and_with_it_off_none_do(self):
        d = dialogue()
        for mood in MOODS:
            for key in self.EVENTS:
                on = d.pool(key, mood, True, False)
                off = d.pool(key, mood, False, False)
                self.assertTrue(any(l.mature for l in on), (key, mood))
                self.assertFalse(any(l.mature for l in off), (key, mood))
                self.assertTrue(off, (key, mood))

    def test_remarks_swear_in_every_mood_when_allowed(self):
        d = dialogue()
        for key in ("Remark_Cute", "Remark_Neutral", "Remark_Snide", "Remark_Sweary", "Remark_Affection"):
            self.assertTrue(any(l.mature for l in d.lines[key]), key)
            self.assertTrue(any(not l.mature for l in d.lines[key]) or key == "Remark_Sweary", key)
        for key in ("PetName_Cute", "PetName_Neutral", "PetName_Snide", "PetName_Affection"):
            self.assertTrue(any(l.mature for l in d.lines[key]), key)

    def test_command_answers_swear_in_every_mood_when_allowed(self):
        d = dialogue()
        for mood in MOODS:
            for key in ("CommandDone", "CommandAlready", "CommandUnknown", "CommandMulti"):
                self.assertTrue(any(l.mature for l in d.pool(key, mood, True, False)), (key, mood))
                self.assertFalse(any(l.mature for l in d.pool(key, mood, False, False)), (key, mood))

    def test_login_and_mood_shift_lines_swear_in_every_mood(self):
        d = dialogue()
        for mood in MOODS:
            self.assertTrue(any(l.mature for l in d.pool("Login_Mood_" + mood, "", True, False)), mood)
            self.assertTrue(any(l.mature for l in d.pool("MoodShift_" + mood, "", True, False)), mood)

    def test_every_command_line_fills_in_for_every_mood(self):
        d = dialogue()
        from control.runner import LINE_FOR_STATUS
        for mood in MOODS:
            for key in set(LINE_FOR_STATUS.values()) | {"CommandMulti"}:
                for line in d.pool(key, mood, True, False):
                    text = line.text.format(doing="Lowering the landing gear", label="the landing gear",
                                            Label="The landing gear", state="down", keys="L", count=2)
                    self.assertNotIn("{", text)


class InnuendoTests(unittest.TestCase):
    def flavour(self, mood="Close", innuendo=True, mature=False, sex="neutral", carried=0, roll=0.0):
        s = make_settings(personality__mood_mode="fixed", personality__mood=mood, speech__allow_mature=mature,
                          personality__remarks="often", personality__innuendo=innuendo, player__sex=sex,
                          personality__dark_humour=False)
        d = dialogue()
        return Flavour(d, s, lambda: carried, rng=Rng(roll), clock=lambda: 0.0), d

    def pool(self, d, key, mature=False):
        return {l.text for k in (key,) for l in d.lines.get(k, []) if mature or not l.mature}

    def test_it_is_off_by_default_and_has_a_dashboard_switch(self):
        self.assertFalse(Settings(Path("nope_x.json")).load().get("personality.innuendo"))
        from ui.settings_model import SettingsModel
        field = SettingsModel(make_settings()).field("personality.innuendo")
        self.assertEqual(field.kind, "toggle")

    def test_off_means_never(self):
        f, d = self.flavour(innuendo=False)
        banned = self.pool(d, "Remark_Innuendo", True)
        for _ in range(30):
            f._last_remark = None
            self.assertFalse(set(part.strip() for part in f.apply("Docked, Commander.", "normal").split("||")) & banned)

    def test_on_and_very_happy_gives_innuendo(self):
        f, d = self.flavour()
        out = f.apply("Docked, Commander.", "normal")
        remark = out.split("||")[-1].strip()
        self.assertIn(remark, self.pool(d, "Remark_Innuendo"))

    def test_naughty_pet_names(self):
        f, d = self.flavour()
        name = f.rename("Docked, Commander.", always=True).split(",")[1].strip(" .")
        self.assertIn(name, self.pool(d, "PetName_Naughty"))

    def test_friendly_gets_it_too_but_less_often(self):
        f, d = self.flavour(mood="Friendly")
        self.assertTrue(f.innuendo_on("Friendly"))
        self.assertLess(f._innuendo_chance("Friendly", 0.55), f._innuendo_chance("Close", 0.55))
        seen = set()
        for _ in range(60):
            f._last_remark = None
            seen.add(f.apply("Docked, Commander.", "normal").split("||")[-1].strip())
        self.assertTrue(seen & self.pool(d, "Remark_Innuendo"))

    def test_only_when_happy(self):
        for mood in ("Neutral", "Sarcastic", "Frustrated"):
            f, d = self.flavour(mood=mood)
            banned = self.pool(d, "Remark_Innuendo", True)
            out = f.apply("Docked, Commander.", "normal")
            self.assertFalse(set(p.strip() for p in out.split("||")) & banned, mood)

    def test_happy_and_rich_also_counts(self):
        f, d = self.flavour(mood="Friendly", carried=600_000_000)
        self.assertTrue(f.innuendo_on("Friendly"))
        self.assertTrue(f.innuendo_on("Neutral"))              # calm but rich in cargo
        poor, _ = self.flavour(mood="Neutral")
        self.assertFalse(poor.innuendo_on("Neutral"))

    def test_the_stronger_lines_need_strong_language(self):
        d = dialogue()
        strong = {l.text for l in d.lines["Remark_Innuendo"] if l.mature}
        self.assertTrue(strong)
        f, _ = self.flavour(mature=False)
        for _ in range(40):
            self.assertNotIn(f._remark("Close"), strong)

    def test_male_and_female_versions(self):
        for sex, key in (("male", "Remark_Innuendo_Male"), ("female", "Remark_Innuendo_Female")):
            f, d = self.flavour(sex=sex)
            self.assertIn(f._remark("Close"), self.pool(d, "Remark_Innuendo") | self.pool(d, key))

    def test_critical_warnings_and_info_style_never_get_it(self):
        f, d = self.flavour()
        self.assertEqual(f.apply("Shields down, Commander.", "critical"), "Shields down, Commander.")
        f.settings.set("personality.style", "info")
        self.assertEqual(f.apply("Docked, Commander.", "normal"), "Docked, Commander.")

    def test_login_greeting_can_flirt(self):
        d = dialogue()
        self.assertTrue(d.lines["Login_Mood_Innuendo"])

    def test_nothing_in_the_innuendo_lines_is_explicit(self):
        # Cheeky double meanings only: keep the lines free of explicit words.
        banned = ("cock", "pussy", "cum ", "dick", "tits", "orgasm", "blowjob", "porn")
        d = dialogue()
        for key, lines in d.lines.items():
            if "Innuendo" in key or "Naughty" in key:
                for line in lines:
                    self.assertFalse(any(re.search(r"\b%s\b" % w.strip(), line.text.lower()) for w in banned), line.text)


if __name__ == "__main__":
    unittest.main()
