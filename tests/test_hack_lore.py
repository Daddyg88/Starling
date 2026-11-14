import tempfile
import unittest
from pathlib import Path

from navigation.hack_after import AfterHack
from navigation.hack_next import NextTarget, parse
from personality.dialogue import DialogueManager
from personality.hack_lore import GROUPS, HackLore
from ui.hack_overlay import bar_text, panel_rows


class Speech:
    def __init__(self):
        self.said = []

    def say(self, text, priority="normal", event_name="", **extra):
        self.said.append(text)
        return True


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def make(path=None):
    d = DialogueManager(pack_dir="voicepacks/default")
    d.load()
    speech = Speech()
    return HackLore(lambda: speech, d, Settings(), path=path), speech


class LoreTests(unittest.TestCase):
    def test_28_chapters(self):
        lore, _ = make()
        self.assertEqual(lore.total(), 28)

    def test_chapters_in_order_per_kind(self):
        lore, speech = make()
        lore.tell("Industrial")
        lore.tell("Industrial")
        self.assertEqual(lore.told["Industrial"], 2)
        self.assertIn(lore.chapters("Industrial")[1], speech.said[1])

    def test_unknown_group_picks_least_told(self):
        lore, _ = make()
        lore.tell("Industrial")
        lore.tell(None)
        self.assertEqual(sum(lore.told.values()), 2)
        self.assertNotEqual(lore.told.get("Industrial"), 2)

    def test_finale_once_after_all(self):
        lore, speech = make()
        for _ in range(40):
            lore.tell(None)
        self.assertTrue(lore.finale)
        self.assertEqual(lore.heard(), 28)
        self.assertEqual(sum("Welcome to the crew" in s for s in speech.said), 1)

    def test_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "l.json"
            lore, _ = make(path)
            lore.tell("Tourist")
            again, _ = make(path)
            self.assertEqual(again.told["Tourist"], 1)

    def test_voice(self):
        lore, speech = make()
        self.assertIsNone(lore.try_handle("what is the time"))
        self.assertIn("no chapter", lore.try_handle("replay the last chapter"))
        lore.tell("Military")
        before = len(speech.said)
        self.assertIsNotNone(lore.try_handle("replay the last chapter"))
        self.assertEqual(len(speech.said), before + 1)
        self.assertIn("1 of 28", lore.try_handle("how many chapters have I heard"))

    def test_no_forbidden_words(self):
        lore, _ = make()
        text = " ".join(c for g in GROUPS for c in lore.chapters(g)).lower()
        self.assertNotIn("payden", text)
        self.assertNotIn("hardpoint", text)


class Mood:
    def __init__(self, moved=True):
        self.moved = moved
        self.calls = []

    def reward(self, points, label):
        self.calls.append((points, label))
        return self.moved


class Narr:
    def __init__(self):
        self.keys = []

    def say(self, key, fields):
        self.keys.append((key, fields))


class Store:
    data = {"1": {"done": True}}


class Next:
    def __init__(self, found):
        self.found = found

    def find(self, system, skip_markets=(), prefer_groups=()):
        self.skip = skip_markets
        return self.found


class AfterTests(unittest.TestCase):
    def run_after(self, result, settings=None, found=None, mood=None):
        lore, speech = make()
        mood = mood or Mood()
        narr = Narr()
        after = AfterHack(Settings(settings or {}), lore, mood, narr, Store(), next_target=Next(found), system_provider=lambda: "Sol",
                          spawn=lambda work: work())
        after(result)
        return lore, mood, narr

    def test_complete_tells_rewards_and_suggests(self):
        found = {"name": "Foo", "system": "Bar", "distance": 12.3, "group": "Military", "market": "9"}
        lore, mood, narr = self.run_after({"how": "complete", "group": "Industrial"}, found=found)
        self.assertEqual(lore.told["Industrial"], 1)
        self.assertEqual(mood.calls, [(6.0, "Base hack")])
        self.assertEqual([k for k, _ in narr.keys], ["Hack_Reward", "Hack_Next"])

    def test_pirate_target_has_its_own_line(self):
        found = {"name": "Foo", "system": "Bar", "distance": 12.3, "group": "Military", "market": "9", "pirate": True}
        _, _, narr = self.run_after({"how": "complete", "group": "Industrial"}, found=found)
        self.assertEqual(narr.keys[-1][0], "Hack_NextPirate")

    def test_timeout_does_nothing(self):
        lore, mood, narr = self.run_after({"how": "timeout", "group": "Industrial"})
        self.assertEqual(lore.told, {})
        self.assertEqual(mood.calls, [])

    def test_switches(self):
        _, mood, narr = self.run_after({"how": "complete", "group": "Tourist"}, settings={"hack.mood": False, "hack.next_target": False})
        self.assertEqual(mood.calls, [])
        self.assertEqual(narr.keys, [])

    def test_nothing_found(self):
        _, _, narr = self.run_after({"how": "complete", "group": "Tourist"}, found=None)
        self.assertEqual(narr.keys[-1][0], "Hack_NextNone")

    def test_frozen_mood_no_reward_line(self):
        _, _, narr = self.run_after({"how": "complete", "group": "Tourist"}, mood=Mood(False))
        self.assertNotIn("Hack_Reward", [k for k, _ in narr.keys])


class NextTests(unittest.TestCase):
    RAW = {"results": [
        {"name": "Far", "system_name": "A", "type": "Odyssey Settlement", "primary_economy": "Industrial", "distance": 30, "market_id": 2},
        {"name": "Near", "system_name": "B", "type": "Odyssey Settlement", "primary_economy": "High Tech", "distance": 5, "market_id": 3},
        {"name": "Done", "system_name": "C", "type": "Odyssey Settlement", "primary_economy": "Military", "distance": 1, "market_id": 1},
        {"name": "Station", "system_name": "D", "type": "Coriolis Starport", "primary_economy": "Military", "distance": 0.5, "market_id": 4},
        "junk"]}

    def test_parse_nearest_not_done_settlements_only(self):
        found = parse(self.RAW, skip_markets={"1"})
        self.assertEqual(found[0]["name"], "Near")
        self.assertEqual(found[0]["group"], "High Tech")

    def test_bad_reply_never_raises(self):
        self.assertEqual(parse(None), [])
        self.assertEqual(parse({"results": "x"}), [])

    def test_find_handles_network_error(self):
        def boom(path, body):
            raise OSError("down")
        self.assertIsNone(NextTarget(post=boom).find("Sol"))
        self.assertIsNone(NextTarget(post=boom).find(None))

    def test_find_uses_and_caches(self):
        calls = []
        nt = NextTarget(post=lambda p, b: calls.append(1) or self.RAW)
        self.assertEqual(nt.find("Sol")["name"], "Done")
        nt.find("Sol")
        self.assertEqual(len(calls), 1)

    def test_pirate_bases_come_first(self):
        raw = {"results": [
            {"name": "Near", "system_name": "B", "type": "Odyssey Settlement", "primary_economy": "Industrial", "distance": 5, "market_id": 3,
             "controlling_minor_faction_government": "Democracy"},
            {"name": "Pirate Den", "system_name": "C", "type": "Odyssey Settlement", "primary_economy": "Military", "distance": 40, "market_id": 5,
             "controlling_minor_faction_government": "Anarchy"}]}
        found = parse(raw, limit=2)
        self.assertEqual([f["name"] for f in found], ["Pirate Den", "Near"])
        self.assertTrue(found[0]["pirate"])
        self.assertFalse(found[1]["pirate"])

    def test_anarchy_filter_refused_falls_back_to_plain_search(self):
        bodies = []

        def post(path, body):
            bodies.append(body)
            if "government" in body["filters"]:
                raise ValueError("unknown filter")
            return self.RAW
        found = NextTarget(post=post).find("Sol")
        self.assertEqual(found["name"], "Done")
        self.assertEqual(len(bodies), 2)
        self.assertNotIn("government", bodies[1]["filters"])


class OverlayTests(unittest.TestCase):
    def test_bar(self):
        self.assertIn("50%", bar_text(0.5))
        self.assertIn("0%", bar_text(None))

    def test_rows(self):
        rows = panel_rows({"name": "Shi", "status": "SCANNING", "progress": 0.4, "items": [("Terminals", 2, 7)]}, 0)
        self.assertEqual(rows[0][0], "EAST ORION COMPANY")
        self.assertTrue(any("Terminals" in r[0] and "2/7" in r[0] for r in rows))


if __name__ == "__main__":
    unittest.main()
