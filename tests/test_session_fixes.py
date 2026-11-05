"""Fixes from the 5 November logs: foreign-language replies, emoticons, YouTube hints, tester names, visited systems."""
import json
import tempfile
import unittest
from datetime import datetime
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


if __name__ == "__main__":
    unittest.main()
