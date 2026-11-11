import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from control.ptt import PushToTalk
from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from memory import habits
from memory.habits import HabitKeeper, ordinal, passed, rapport
from personality.chitchat import ChitChat, people_text
from personality.dialogue import DialogueManager
from tests.test_chitchat import Speech


class Day:
    """A clock for the keeper: the date can be moved on."""
    def __init__(self, day=datetime(2026, 11, 11, 20, 0)):
        self.day = day

    def __call__(self):
        return self.day

    def next_day(self, n=1):
        self.day += timedelta(days=n)


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "habits.json"
        self.said = []
        self.calendar = Day()
        self.t = [1000.0]
        self.jumps = [0]
        self.hours = [0.0]
        self.system = ["Sol"]
        self.keeper = self.make()

    def make(self, **kw):
        return HabitKeeper(None, self.path, announce=lambda key, values: self.said.append((key, values)) or True, now=self.calendar,
                           clock=lambda: self.t[0], hours=lambda: self.hours[0], jumps=lambda: self.jumps[0],
                           system=lambda: self.system[0], **kw)

    def fire(self, name, **data):
        self.keeper.on_event(SimpleNamespace(name=name, data=data))

    def dock(self, station="Jameson Memorial"):
        self.fire("Docked", StationName=station)

    def keys(self):
        return [k for k, _ in self.said]


class Helpers(unittest.TestCase):
    def test_ordinals(self):
        self.assertEqual([ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 103)], ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "103rd"])

    def test_rapport_stages(self):
        self.assertEqual([rapport(h) for h in (0, 24.9, 25, 99, 100, 999, 1000, "x", None)],
                         ["new", "new", "crew", "crew", "friend", "friend", "family", "new", "new"])

    def test_passed(self):
        self.assertEqual(passed(habits.JUMP_STEPS, 99), 0)
        self.assertEqual(passed(habits.JUMP_STEPS, 600), 500)

    def test_people_text(self):
        self.assertEqual(people_text(4_200_000_000), "4.2 billion")
        self.assertEqual(people_text(1_500_000), "1.5 million")
        self.assertEqual(people_text(12345), "12,345")


class Stations(Env):
    def test_third_landing_this_week_is_remarked_on_once(self):
        self.dock()
        self.dock()
        self.assertEqual(self.said, [])
        self.dock()
        self.assertEqual(self.keys(), ["Habit_Station_Week"])
        self.assertEqual(self.said[0][1]["station"], "Jameson Memorial")
        self.assertEqual(self.said[0][1]["ordinal"], "3rd")
        self.dock()
        self.assertEqual(len(self.said), 1)                       # the 4th is not a step

    def test_one_habit_remark_per_twenty_minutes(self):
        for _ in range(3):
            self.dock()
        self.assertEqual(len(self.said), 1)
        for _ in range(2):
            self.dock()                                            # the 5th landing is a step, but it is too soon
        self.assertEqual(len(self.said), 1)

    def test_after_the_gap_she_may_speak_again(self):
        for _ in range(3):
            self.dock()
        self.t[0] += habits.REMARK_GAP_SECONDS + 1
        self.dock()
        self.dock()
        self.assertEqual(self.keys(), ["Habit_Station_Week", "Habit_Station_Week"])
        self.assertEqual(self.said[1][1]["count"], 5)

    def test_old_landings_do_not_count_towards_this_week(self):
        for _ in range(2):
            self.dock()
        self.calendar.next_day(9)
        self.dock()
        self.assertEqual(self.said, [])

    def test_the_tenth_landing_is_home(self):
        for number in range(10):
            self.calendar.next_day(4)                              # never three in a week
            self.dock()
        self.assertEqual(self.keys(), ["Habit_Station_Home"])
        self.assertEqual(self.said[0][1]["count"], 10)

    def test_different_stations_are_counted_separately(self):
        for name in ("A", "B", "A", "B", "A", "B"):
            self.dock(name)
        self.assertEqual(self.keeper.stations["A"]["count"], 3)
        self.assertEqual(self.keeper.stations["B"]["count"], 3)

    def test_a_docked_event_without_a_station_is_ignored(self):
        self.fire("Docked")
        self.assertEqual(self.keeper.stations, {})

    def test_the_favourite_station(self):
        self.assertIsNone(self.keeper.favourite_station())
        for number in range(8):
            self.dock("Home Base")
        self.assertEqual(self.keeper.favourite_station(), ("Home Base", 8))
        self.assertEqual(self.keeper.context()["fav_station"], "Home Base")


class Deaths(Env):
    def test_the_first_death_in_a_system_is_not_remarked_on(self):
        self.fire("Died")
        self.fire("Resurrect")
        self.assertEqual(self.said, [])

    def test_the_second_death_is_remarked_on_when_you_are_back(self):
        self.fire("Died")
        self.fire("Resurrect")
        self.t[0] += 10
        self.fire("Died")
        self.assertEqual(self.said, [])                            # not while the death screen is up
        self.fire("Resurrect")
        self.assertEqual(self.keys(), ["Habit_Death_Place"])
        self.assertEqual((self.said[0][1]["system"], self.said[0][1]["count"], self.said[0][1]["ordinal"]), ("Sol", 2, "2nd"))

    def test_deaths_elsewhere_are_counted_apart(self):
        self.fire("Died")
        self.system[0] = "Colonia"
        self.fire("Died")
        self.fire("Resurrect")
        self.assertEqual(self.said, [])


class Streaks(Env):
    def test_three_days_in_a_row_is_said_at_the_next_calm_moment(self):
        for day in range(3):
            self.fire("LoadGame")
            self.keeper._session_day = None
            if day < 2:
                self.calendar.next_day()
        self.assertEqual(self.keeper.streak(), 3)
        self.assertEqual(self.said, [])                            # not during the login greeting
        self.fire("Docked", StationName="X")
        self.assertEqual(self.keys(), ["Habit_Streak"])
        self.assertEqual(self.said[0][1]["days"], 3)
        self.fire("FSDJump")
        self.assertEqual(len(self.said), 1)                        # once

    def test_a_missed_day_breaks_the_streak(self):
        self.fire("LoadGame")
        self.calendar.next_day(2)
        self.keeper._session_day = None
        self.fire("LoadGame")
        self.assertEqual(self.keeper.streak(), 1)

    def test_loading_twice_in_a_day_is_one_day(self):
        self.fire("LoadGame")
        self.fire("LoadGame")
        self.assertEqual(self.keeper.days, ["2026-11-11"])


class Milestones(Env):
    def test_a_first_start_does_not_announce_what_is_already_behind_you(self):
        self.jumps[0], self.hours[0] = 700, 60.0
        self.path.unlink() if self.path.exists() else None
        keeper = self.make()
        self.assertEqual(keeper.told["jumps"], 500)
        self.assertEqual(keeper.told["hours"], 50)
        keeper.on_event(SimpleNamespace(name="FSDJump", data={}))
        self.assertEqual(self.said, [])

    def test_the_next_jump_milestone_is_said(self):
        self.jumps[0] = 99
        self.keeper = self.make()
        self.jumps[0] = 100
        self.fire("FSDJump")
        self.assertEqual(self.keys(), ["Habit_Jumps"])
        self.assertEqual(self.said[0][1]["count"], "100")
        self.fire("FSDJump")
        self.assertEqual(len(self.said), 1)

    def test_hours_together_milestone(self):
        self.hours[0] = 4.9
        self.keeper = self.make()
        self.hours[0] = 5.1
        self.fire("FSDJump")
        self.assertEqual(self.keys(), ["Rapport_Hours"])
        self.assertEqual(self.said[0][1]["hours"], 5)

    def test_a_remark_that_could_not_be_spoken_is_tried_again(self):
        self.jumps[0] = 99
        self.keeper = self.make()
        self.keeper.announce = lambda key, values: False
        self.jumps[0] = 100
        self.fire("FSDJump")
        self.keeper.announce = lambda key, values: self.said.append((key, values)) or True
        self.fire("FSDJump")
        self.assertEqual(self.keys(), ["Habit_Jumps"])


class Saving(Env):
    def test_what_she_noticed_survives_a_restart(self):
        for _ in range(3):
            self.dock("Jameson Memorial")
        self.fire("Died")
        self.keeper.flush()
        again = self.make()
        self.assertEqual(again.stations["Jameson Memorial"]["count"], 3)
        self.assertEqual(again.deaths, {"Sol": 1})

    def test_a_broken_or_odd_file_is_ignored(self):
        for text in ("not json", "[1, 2]", json.dumps({"stations": {"A": "x", "B": {"count": "many"}}, "deaths": {"S": -1}, "days": [1, "2026-01-01"], "told": {"jumps": "a"}})):
            self.path.write_text(text, encoding="utf-8")
            keeper = self.make()
            self.assertEqual(keeper.stations, {})
            self.assertEqual(keeper.deaths, {})

    def test_it_can_be_switched_off(self):
        keeper = HabitKeeper(None, self.path, announce=lambda k, v: self.said.append(k), now=self.calendar, enabled=lambda: False)
        for _ in range(5):
            keeper.on_event(SimpleNamespace(name="Docked", data={"StationName": "X"}))
        self.assertEqual((keeper.stations, self.said), ({}, []))

    def test_forget_everything(self):
        for _ in range(3):
            self.dock()
        self.keeper.clear()
        self.assertEqual((self.keeper.stations, self.keeper.deaths, self.keeper.days), ({}, {}, []))
        self.assertEqual(self.make().stations, {})

    def test_names_are_kept_short_and_the_list_does_not_grow_forever(self):
        self.dock("X" * 500)
        self.assertTrue(all(len(name) <= habits.MAX_NAME for name in self.keeper.stations))
        for number in range(habits.MAX_STATIONS + 50):
            self.dock("Station %d" % number)
        self.assertLessEqual(len(self.keeper.stations), habits.MAX_STATIONS)


class Chatter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.t = [1000.0]
        self.hour = [14]
        self.speech = Speech()
        self.state = SimpleNamespace(docked=False, in_supercruise=False, system="Sol", system_security="High Security",
                                     system_allegiance="Federation", system_population=22_780_919_531)
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", rng=random.Random(3)).load()
        self.chat = ChitChat(EventBus(), self.speech, self.dialogue, self.settings, lambda: self.state, lambda: True,
                             clock=lambda: self.t[0], rng=random.Random(1), wall=lambda: datetime(2026, 11, 11, self.hour[0], 40))

    def keys(self):
        self.t[0] += 3000
        return self.chat.candidate_keys()

    def test_late_at_night_after_twenty_minutes(self):
        self.hour[0] = 2
        self.assertIn("ChitChat_Late", self.keys())

    def test_not_late_when_the_session_has_just_begun(self):
        self.hour[0] = 2
        self.t[0] += 60
        self.assertNotIn("ChitChat_Late", self.chat.candidate_keys())

    def test_early_morning_and_ordinary_hours(self):
        self.hour[0] = 6
        self.assertIn("ChitChat_Early", self.keys())
        self.hour[0] = 14
        keys = self.keys()
        self.assertNotIn("ChitChat_Early", keys)
        self.assertNotIn("ChitChat_Late", keys)

    def test_the_system_she_is_in(self):
        self.assertIn("ChitChat_World", self.keys())
        values = self.chat.context()
        self.assertEqual((values["security"], values["allegiance"], values["population"]), ("high security", "Federation", "22.8 billion"))

    def test_no_system_facts_no_world_remark(self):
        self.state = SimpleNamespace(docked=False, in_supercruise=False)
        self.assertNotIn("ChitChat_World", self.keys())

    def test_she_does_not_repeat_the_same_kind_of_remark_for_twenty_minutes(self):
        self.t[0] += 3000
        self.chat.state_said["ChitChat_World"] = self.t[0]
        self.assertNotIn("ChitChat_World", self.chat.candidate_keys())

    def test_the_whole_thing_can_be_switched_off(self):
        self.settings.set("chitchat.world", False)
        self.hour[0] = 2
        keys = self.keys()
        self.assertFalse([k for k in keys if k in ("ChitChat_Late", "ChitChat_World", "ChitChat_Habits")])

    def test_habits_and_rapport_come_from_the_keeper(self):
        self.chat.habits = SimpleNamespace(context=lambda: {"fav_station": "Jameson Memorial", "fav_count": 12, "rapport": "friend"})
        keys = self.keys()
        self.assertIn("ChitChat_Habits", keys)
        self.assertIn("ChitChat_Rapport_Friend", keys)
        self.assertEqual(self.chat.context()["fav_station"], "Jameson Memorial")

    def test_a_new_friend_gets_no_rapport_remark(self):
        self.chat.habits = SimpleNamespace(context=lambda: {"rapport": "new"})
        self.assertFalse([k for k in self.keys() if k.startswith("ChitChat_Rapport")])

    def test_a_broken_habit_keeper_does_not_stop_chatter(self):
        def boom():
            raise RuntimeError("no")
        self.chat.habits = SimpleNamespace(context=boom)
        self.assertTrue(self.keys())

    def test_in_a_fight_none_of_it_is_said(self):
        self.chat.mode = "combat"
        self.hour[0] = 2
        self.assertEqual(self.keys(), ["ChitChat_Combat"])

    def test_her_lines_use_the_values_she_has(self):
        self.hour[0] = 2
        self.chat.habits = SimpleNamespace(context=lambda: {"fav_station": "Jameson Memorial", "fav_count": 12, "days_in_row": 4, "rapport": "crew"})
        said = set()
        for number in range(80):
            self.t[0] += 5000
            self.chat.state_said.clear()
            self.chat.last_chat = -1e9
            self.chat.last_spoke = -1e9
            text = self.chat.tick(self.t[0])
            if text:
                said.add(text)
        self.assertTrue(said)
        for text in said:
            self.assertNotIn("{", text)
            self.assertNotIn("Payden", text)


class PushToTalkInterrupt(unittest.TestCase):
    class Reader:
        def __init__(self): self.down = False
        def is_down(self, button): return self.down

    def make(self, **settings):
        values = {"ptt.mode": "hold", "ptt.button": "1", "ptt.beep": False}
        values.update(settings)
        stopped = []
        s = SimpleNamespace(get=lambda key, default=None: values.get(key, default))
        reader = self.Reader()
        return PushToTalk(s, reader, on_open=lambda: stopped.append(1)), reader, stopped

    def test_pressing_the_button_stops_her_talking_and_releasing_does_not(self):
        ptt, reader, stopped = self.make()
        reader.down = True
        ptt.poll_once()
        self.assertEqual(stopped, [1])
        reader.down = False
        ptt.poll_once()
        self.assertEqual(stopped, [1])

    def test_it_can_be_switched_off(self):
        ptt, reader, stopped = self.make(**{"speech.ptt_interrupts": False})
        reader.down = True
        ptt.poll_once()
        self.assertEqual(stopped, [])

    def test_a_failing_stop_does_not_break_the_button(self):
        ptt, reader, _ = self.make()
        ptt.on_open = lambda: 1 / 0
        reader.down = True
        ptt.poll_once()
        self.assertTrue(ptt.is_open())


class TheWords(unittest.TestCase):
    LINES = json.loads((Path(__file__).resolve().parent.parent / "voicepacks" / "default" / "habits.json").read_text(encoding="utf-8"))
    ALLOWED = {"station", "count", "ordinal", "system", "days", "hours", "stage"}

    def test_every_remark_has_lines_and_only_known_values(self):
        import re
        for key in ("Habit_Station_Week", "Habit_Station_Home", "Habit_Death_Place", "Habit_Streak", "Habit_Jumps", "Rapport_Hours"):
            self.assertGreaterEqual(len(self.LINES[key]), 3, key)
        for key, lines in self.LINES.items():
            for text in lines:
                for name in re.findall(r"{(\w+)}", text):
                    self.assertIn(name, self.ALLOWED, text)


if __name__ == "__main__":
    unittest.main()
