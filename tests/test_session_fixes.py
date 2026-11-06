"""Fixes from the 5 November logs: foreign-language replies, emoticons, YouTube hints, tester names, visited systems."""
import json
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from pathlib import Path

from core.event_bus import Event
from memory.stats import StatsKeeper
from personality.llm import looks_foreign
from streaming.bridge import ChatBridge
from streaming.chat import tidy

VOICEPACKS = Path(__file__).resolve().parent.parent / "voicepacks"


def ev(name, **data):
    return Event(name=name, data=data)


class FilterTests(unittest.TestCase):
    def test_french_is_caught(self):
        self.assertTrue(looks_foreign("je suis désolé, je ne peux pas répondre à cela"))
        self.assertFalse(looks_foreign("we are almost at the next star, commander"))

    def test_emoticons_and_emoji_are_stripped(self):
        out = tidy("hello there :D \U0001F600 how are you")
        self.assertNotIn(":D", out)
        self.assertNotIn("\U0001F600", out)
        self.assertIn("hello there", out)


class YouTubeNoteTests(unittest.TestCase):
    def test_half_set_up_gives_plain_hints(self):
        notes = ChatBridge._youtube_notes
        self.assertEqual(notes(False, "", "", None), [])
        self.assertTrue(notes(True, "", "https://youtu.be/abcdefghijk", "abcdefghijk")[0].startswith("YouTube: add your"))
        self.assertIn("paste the link", notes(True, "AIza" + "x" * 35, "", None)[0])
        self.assertIn("doesn't look like a live stream link", notes(True, "AIza" + "x" * 35, "nonsense", None)[0])


class TesterNameTests(unittest.TestCase):
    def test_no_voice_line_names_a_tester(self):
        bad = ("curd nerd", "curdnerd")
        for file in (VOICEPACKS / "default").glob("*.json"):
            if file.name == "eoc.json":
                continue
            text = file.read_text(encoding="utf-8").lower()
            for name in bad:
                self.assertNotIn(name, text, "%s mentions %s" % (file.name, name))


class VisitedSystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.said = []
        self.now = [0.0]
        self.keeper = StatsKeeper(None, Path(self.tmp.name) / "stats.json", announce=lambda k, v: self.said.append((k, v)),
                                  now=lambda: datetime(2026, 11, 5), clock=lambda: self.now[0])

    def test_scanned_system_is_recognised_on_return(self):
        self.keeper.on_event(ev("FSDJump", StarSystem="Alpha"))
        self.keeper.on_event(ev("Scan", BodyName="Alpha 1", StarSystem="Alpha"))
        self.keeper.on_event(ev("Scan", BodyName="Alpha 2"))               # no system in the event: uses where we are
        self.assertEqual(self.keeper.scanned_here("Alpha"), 2)
        self.assertEqual(self.said, [])                                    # the first visit says nothing
        self.now[0] = 5000.0
        self.keeper.on_event(ev("FSDJump", StarSystem="Alpha"))
        self.assertEqual(self.said[-1][0], "Stats_Revisit_Scanned")
        self.assertEqual(self.said[-1][1]["Bodies"], 2)

    def test_not_chatty_about_returns(self):
        self.keeper.on_event(ev("FSDJump", StarSystem="A"))
        self.keeper.on_event(ev("FSDJump", StarSystem="B"))
        self.keeper.on_event(ev("FSDJump", StarSystem="A"))
        self.keeper.on_event(ev("FSDJump", StarSystem="B"))
        self.assertEqual(len(self.said), 1)                                # the cooldown stops a string of remarks

    def test_old_journals_are_read_once_and_capped(self):
        folder = Path(self.tmp.name) / "j"
        folder.mkdir()
        compact = lambda entry: json.dumps(entry, separators=(",", ":"))      # real journals have no spaces
        lines = [compact({"timestamp": "2026-10-01T10:00:00Z", "event": "FSDJump", "StarSystem": "Old One"}),
                 compact({"timestamp": "2026-10-01T10:05:00Z", "event": "Scan", "ScanType": "Detailed", "BodyName": "Old One 1"}),
                 compact({"timestamp": "2026-10-02T10:05:00Z", "event": "Scan", "ScanType": "NavBeaconDetail", "StarSystem": "Beacon"}),
                 "not json {"]
        (folder / "Journal.2026-10-01.01.log").write_text("\n".join(lines), encoding="utf-8")
        self.keeper.scan_history(folder)
        self.assertTrue(self.keeper.history_done)
        self.assertEqual(self.keeper.visit_info("Old One"), (1, ""))
        self.assertEqual(self.keeper.scanned_here("Old One"), 1)
        self.assertNotIn("Beacon", self.keeper.visits)
        (folder / "Journal.2026-10-03.01.log").write_text(lines[0].replace("Old One", "New Two"), encoding="utf-8")
        self.keeper.scan_history(folder)                                   # done already: reads nothing
        self.assertNotIn("New Two", self.keeper.visits)

    def test_cap_drops_the_oldest(self):
        import memory.stats as stats
        old_max, old_trim = stats.MAX_SYSTEMS, stats.TRIM_BY
        stats.MAX_SYSTEMS, stats.TRIM_BY = 10, 3
        self.addCleanup(lambda: (setattr(stats, "MAX_SYSTEMS", old_max), setattr(stats, "TRIM_BY", old_trim)))
        self.keeper.seed({"S%d" % i: (1, "2026-10-%02d" % (i + 1), 0) for i in range(12)})
        self.assertLessEqual(len(self.keeper.visits), 10)
        self.assertNotIn("S0", self.keeper.visits)
        self.assertIn("S11", self.keeper.visits)


class SnappyVoiceTests(unittest.TestCase):
    def test_lines_are_split_into_cacheable_sentences(self):
        from tts.kokoro_tts import sentences_of
        self.assertEqual(sentences_of("Neutron star reached. Supercharge, then head for Foo, 4 jumps."),
                         ["Neutron star reached.", "Supercharge, then head for Foo, 4 jumps."])
        self.assertEqual(sentences_of("Oh. That was close, Commander."), ["Oh. That was close, Commander."])   # too short to stand alone
        self.assertEqual(sentences_of("One line only"), ["One line only"])

    def test_mining_lines_are_prepared_for_favourites(self):
        import random
        from core import paths
        from personality.dialogue import DialogueManager
        from tts.voice_warmer import mining_texts
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"], rng=random.Random(1)).load()
        texts = mining_texts(dialogue, False, None)
        self.assertGreater(len(texts), 100)
        self.assertTrue(all("{" not in t for t in texts))
        self.assertIn("Grandidierite", " ".join(texts))
        self.assertTrue(any("tonnes" in t and "5" in t for t in texts))


class WatcherBackoffTests(unittest.TestCase):
    def test_retry_delay_grows_then_stops_at_two_minutes(self):
        from personality.watcher import WatcherBridge
        bridge = WatcherBridge.__new__(WatcherBridge)          # only the waiting rule is tested
        delays = [bridge.retry_delay() for _ in range(8)]
        self.assertEqual(delays[:4], [10.0, 20.0, 40.0, 80.0])
        self.assertEqual(delays[-1], 120.0)


class MissionMemoryTests(unittest.TestCase):
    def test_only_the_payout_is_spoken(self):
        from memory.recall import spoken_summary
        memory = {"memory_type": "big_mission", "summary": "a mission worth 5.1 million credits: Expansion Support by Killing Known Terrorist: Oliver"}
        self.assertEqual(spoken_summary(memory), "a mission worth 5.1 million credits")
        self.assertEqual(spoken_summary({"memory_type": "death", "summary": "You were destroyed: oops"}), "You were destroyed: oops")


class VoidRunningTests(unittest.TestCase):
    def test_running_means_answered_recently(self):
        import time
        from personality.watcher import WatcherBridge
        bridge = WatcherBridge.__new__(WatcherBridge)
        bridge.last_ok = None
        self.assertFalse(bridge.void_compass_running())
        bridge.last_ok = time.monotonic()
        self.assertTrue(bridge.void_compass_running())
        bridge.last_ok = time.monotonic() - 100
        self.assertFalse(bridge.void_compass_running())


class LinePickerTests(unittest.TestCase):
    def make(self, lines):
        import random
        from personality.dialogue import DialogueManager
        manager = DialogueManager(rng=random.Random(3))
        manager._merge(lines)
        return manager

    def test_same_words_under_another_key_are_avoided(self):
        manager = self.make({"B": ["Shared line one", "B two", "B three", "B four", "B five"]})
        manager._spoken.append("Shared line one")
        for _ in range(3):                                       # while there are other lines to use, the shared one waits
            self.assertNotEqual(manager.pick("B").text, "Shared line one")

    def test_the_same_opening_is_avoided_when_there_is_a_choice(self):
        manager = self.make({"A": ["Nice work on that one.", "Nice work again.", "Brilliant, Commander."]})
        manager._spoken.append("Nice work, Commander.")
        self.assertEqual(manager.pick("A").text, "Brilliant, Commander.")

    def test_never_stuck_with_one_line(self):
        manager = self.make({"A": ["Only one."]})
        manager._spoken.append("Only one.")
        self.assertEqual(manager.pick("A").text, "Only one.")

    def test_memory_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "recent.json"
            lines = {"A": ["One.", "Two.", "Three.", "Four."]}
            first = self.make(lines).attach_memory(file)
            said = [first.pick("A").text for _ in range(3)]
            first.save_memory()
            second = self.make(lines).attach_memory(file)
            self.assertEqual(second.pick("A").text, ({"One.", "Two.", "Three.", "Four."} - set(said)).pop())


class VoiceLoadingTests(unittest.TestCase):
    def test_model_check_looks_for_downloaded_files(self):
        import os
        from tts.kokoro_tts import KokoroTTS
        with tempfile.TemporaryDirectory() as folder:
            old = os.environ.get("HF_HUB_CACHE")
            os.environ["HF_HUB_CACHE"] = folder
            try:
                self.assertFalse(KokoroTTS.model_is_downloaded())
                snap = Path(folder) / "models--hexgrad--Kokoro-82M" / "snapshots" / "abc"
                snap.mkdir(parents=True)
                (snap / "config.json").write_text("{}")
                self.assertTrue(KokoroTTS.model_is_downloaded())
            finally:
                if old is None:
                    os.environ.pop("HF_HUB_CACHE", None)
                else:
                    os.environ["HF_HUB_CACHE"] = old

    def test_loading_time_is_reported_while_loading(self):
        import time
        from tts.kokoro_tts import KokoroTTS
        tts = KokoroTTS.__new__(KokoroTTS)
        import threading
        tts.ready, tts.failed_reason, tts._load_started = threading.Event(), "", None
        self.assertEqual(tts.loading_seconds(), 0.0)
        tts._load_started = time.monotonic() - 30
        self.assertGreaterEqual(tts.loading_seconds(), 29)
        tts.ready.set()
        self.assertEqual(tts.loading_seconds(), 0.0)


class HelperOrderTests(unittest.TestCase):
    def runner(self):
        from types import SimpleNamespace
        from control.runner import CommandRunner
        r = CommandRunner.__new__(CommandRunner)
        r.extra_helpers = []
        r.smalltalk = SimpleNamespace(try_handle=lambda t: None)
        r.memory = None
        r.route = SimpleNamespace(try_handle=lambda t: None)
        return r

    def test_order_is_extras_then_small_talk_memory_route(self):
        r = self.runner()
        a, b = SimpleNamespace(try_handle=lambda t: None), SimpleNamespace(try_handle=lambda t: None)
        r.add_helper(a)
        r.add_helper(b, first=True)
        helpers = [h for _, h in r.voice_helpers()]
        self.assertEqual(helpers, [b, a, r.smalltalk, r.route])          # a missing helper (memory) is simply left out


if __name__ == "__main__":
    unittest.main()
