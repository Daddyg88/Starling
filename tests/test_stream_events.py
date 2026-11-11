import json
import re
import unittest
from pathlib import Path

from streaming import chat, events, twitch, youtube
from streaming.bridge import ChatBridge
from tests.test_streaming import Clock, Settings, ship_state, msg


def notice(msg_id, **tags):
    """A Twitch USERNOTICE line as the chat server sends it."""
    tag_text = ";".join(["msg-id=%s" % msg_id] + ["%s=%s" % (k.replace("_", "-"), v) for k, v in tags.items()])
    return "@%s :tmi.twitch.tv USERNOTICE #daddyg88 :hello" % tag_text


def make(quiet=True, **settings):
    clock = Clock()
    said = []
    base = {"enabled": True}
    base.update(settings)
    state = {"quiet": quiet}
    director = chat.ChatDirector(Settings(**base), lambda: ship_state(), lambda a: True, lambda u, q: True,
                                 lambda key, fields=None: said.append((key, fields)), clock, quiet_provider=lambda: state["quiet"])
    return director, clock, said, state


class TwitchNotices(unittest.TestCase):
    def event(self, line):
        return events.from_twitch(twitch.parse_line(line))

    def test_a_sub(self):
        e = self.event(notice("sub", display_name="Gav"))
        self.assertEqual((e.kind, e.user, e.platform), ("sub", "Gav", "twitch"))

    def test_a_resub_has_the_months(self):
        e = self.event(notice("resub", display_name="Gav", msg_param_cumulative_months="14"))
        self.assertEqual((e.kind, e.amount), ("resub", 14))

    def test_gifts(self):
        self.assertEqual(self.event(notice("subgift", display_name="Gav")).amount, 1)
        big = self.event(notice("submysterygift", display_name="Gav", msg_param_mass_gift_count="25"))
        self.assertEqual((big.kind, big.amount), ("gift", 25))
        self.assertEqual(self.event(notice("anonsubgift")).user, "an anonymous viewer")

    def test_a_raid(self):
        e = self.event(notice("raid", display_name="Woz", msg_param_displayName="Woz", msg_param_viewerCount="42"))
        self.assertEqual((e.kind, e.user, e.amount), ("raid", "Woz", 42))

    def test_a_watch_streak_but_not_other_milestones(self):
        e = self.event(notice("viewermilestone", display_name="Gav", msg_param_category="watch-streak", msg_param_value="7"))
        self.assertEqual((e.kind, e.amount), ("streak", 7))
        self.assertIsNone(self.event(notice("viewermilestone", display_name="Gav", msg_param_category="something-else", msg_param_value="7")))

    def test_other_notices_and_messages_are_ignored(self):
        self.assertIsNone(self.event(notice("announcement", display_name="Gav")))
        self.assertIsNone(self.event("@display-name=Gav :gav!gav@gav.tmi.twitch.tv PRIVMSG #daddyg88 :!lights"))

    def test_names_and_numbers_are_made_safe(self):
        e = self.event(notice("raid", display_name="Evil\\s<b>Name</b>\\:rm\\s-rf", msg_param_viewerCount="99999999999999"))
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_ ]{1,25}", e.user), e.user)
        self.assertEqual(e.amount, events.MAX_NUMBER)
        self.assertEqual(self.event(notice("resub", display_name="Gav", msg_param_cumulative_months="banana")).amount, 2)

    def test_the_twitch_reader_hands_events_on(self):
        got = []
        reader = twitch.TwitchChat("daddyg88", got.append, lambda text: None)
        reader._handle(notice("sub", display_name="Gav"), None)
        self.assertEqual([e.kind for e in got], ["sub"])


class YouTubeEvents(unittest.TestCase):
    def test_super_chats_members_and_gifts(self):
        page = {"items": [
            {"snippet": {"type": "superChatEvent"}, "authorDetails": {"displayName": "Anna"}},
            {"snippet": {"type": "newSponsorEvent"}, "authorDetails": {"displayName": "Ben"}},
            {"snippet": {"type": "memberMilestoneChatEvent", "memberMilestoneChatDetails": {"memberMonth": 6}}, "authorDetails": {"displayName": "Cat"}},
            {"snippet": {"type": "membershipGiftingEvent", "membershipGiftingDetails": {"giftMembershipsCount": 5}}, "authorDetails": {"displayName": "Dan"}},
            {"snippet": {"type": "textMessageEvent"}, "authorDetails": {"displayName": "Eve"}},
        ]}
        got = youtube.parse_events(page)
        self.assertEqual([(e.kind, e.user, e.amount) for e in got],
                         [("tip", "Anna", 0), ("sub", "Ben", 0), ("resub", "Cat", 6), ("gift", "Dan", 5)])

    def test_the_amount_of_money_is_never_part_of_the_event(self):
        page = {"items": [{"snippet": {"type": "superChatEvent", "superChatDetails": {"amountDisplayString": "$50.00"}},
                           "authorDetails": {"displayName": "Anna"}}]}
        self.assertNotIn("50", repr(youtube.parse_events(page)))


class Reacting(unittest.TestCase):
    def test_she_thanks_a_new_sub_when_it_is_quiet(self):
        director, clock, said, _ = make()
        director.react(events.StreamEvent("sub", "Gav"))
        self.assertEqual(said, [("StreamEvent_Sub", {"user": "Gav", "amount": 0, "months": 0, "viewers": "a whole crowd of", "streak": 0,
                                                     "count": 0, "people": 0, "messages": 0, "platform": ""})])

    def test_it_waits_while_she_is_busy_and_is_then_said_once(self):
        director, clock, said, state = make(quiet=False)
        director.react(events.StreamEvent("raid", "Woz", 30))
        self.assertEqual(said, [])
        state["quiet"] = True
        director.pump_events()
        director.pump_events()
        self.assertEqual([k for k, _ in said], ["StreamEvent_Raid"])
        self.assertEqual(said[0][1]["viewers"], 30)

    def test_old_news_is_dropped(self):
        director, clock, said, state = make(quiet=False)
        director.react(events.StreamEvent("sub", "Gav"))
        clock.now += 301
        state["quiet"] = True
        director.pump_events()
        self.assertEqual(said, [])
        self.assertEqual(director.pending_count() if hasattr(director, "pending_count") else len(director.pending), 0)

    def test_a_big_raid_and_a_big_gift_use_the_bigger_pools(self):
        self.assertEqual(events.pick_pool(events.StreamEvent("raid", "W", 80)), "StreamEvent_Raid_Big")
        self.assertEqual(events.pick_pool(events.StreamEvent("raid", "W", 8)), "StreamEvent_Raid")
        self.assertEqual(events.pick_pool(events.StreamEvent("gift", "W", 10)), "StreamEvent_Gift_Big")
        self.assertEqual(events.pick_pool(events.StreamEvent("resub", "W", 24)), "StreamEvent_Resub_Long")

    def test_a_missing_big_pool_falls_back_to_the_ordinary_one(self):
        said = []
        director, clock, _, _ = make()
        director.say = lambda key, fields=None: said.append(key) or (key == "StreamEvent_Gift")
        director.react(events.StreamEvent("gift", "Gav", 12))
        self.assertEqual(said, ["StreamEvent_Gift_Big", "StreamEvent_Gift"])

    def test_a_mass_gift_is_said_once_not_once_per_sub(self):
        director, clock, said, _ = make()
        director.react(events.StreamEvent("gift", "Gav", 20))
        for _ in range(20):
            clock.now += 0.2
            director.react(events.StreamEvent("gift", "Gav", 1))
        self.assertEqual([k for k, _ in said], ["StreamEvent_Gift_Big"])

    def test_the_same_kind_is_not_said_twice_in_a_row(self):
        director, clock, said, _ = make()
        director.react(events.StreamEvent("sub", "A"))
        director.react(events.StreamEvent("sub", "B"))
        self.assertEqual(len(said), 1)
        clock.now += 9
        director.pump_events()
        self.assertEqual([f["user"] for _, f in said], ["A", "B"])

    def test_the_switches(self):
        director, clock, said, _ = make(react=False)
        self.assertFalse(director.react(events.StreamEvent("sub", "Gav")))
        director, clock, said, _ = make(enabled=False)
        self.assertFalse(director.react(events.StreamEvent("sub", "Gav")))
        self.assertEqual(said, [])

    def test_unknown_kinds_are_ignored(self):
        director, clock, said, _ = make()
        self.assertFalse(director.react(events.StreamEvent("explode", "Gav")))

    def test_too_many_waiting_drops_the_oldest(self):
        director, clock, said, _ = make(quiet=False)
        for number in range(10):
            director.react(events.StreamEvent("sub", "User%d" % number))
        self.assertEqual(len(director.pending), director.MAX_PENDING)
        self.assertEqual(director.pending[0][1].user, "User4")


class ChatMilestones(unittest.TestCase):
    def test_round_numbers(self):
        self.assertEqual(events.next_milestone("chat_messages", 49, 0), 0)
        self.assertEqual(events.next_milestone("chat_messages", 50, 0), 50)
        self.assertEqual(events.next_milestone("chat_messages", 120, 50), 100)
        self.assertEqual(events.next_milestone("chat_messages", 1499, 1000), 0)
        self.assertEqual(events.next_milestone("chat_messages", 1500, 1000), 1500)
        self.assertEqual(events.next_milestone("chat_people", 25, 10), 25)

    def test_chat_messages_are_counted_and_the_50th_is_remarked_on(self):
        director, clock, said, _ = make()
        for number in range(50):
            clock.now += 1
            director.handle(msg("hello there", user="Viewer%d" % (number % 7)))
        keys = [k for k, _ in said]
        self.assertIn("StreamEvent_ChatMessages", keys)
        self.assertEqual(keys.count("StreamEvent_ChatMessages"), 1)
        self.assertEqual([f["messages"] for k, f in said if k == "StreamEvent_ChatMessages"], [50])

    def test_different_people_are_counted(self):
        director, clock, said, _ = make()
        for number in range(5):
            clock.now += 1
            director.handle(msg("hi", user="Viewer%d" % number))
        self.assertIn("StreamEvent_ChatPeople", [k for k, _ in said])

    def test_a_flood_from_one_person_is_not_many_people(self):
        director, clock, said, _ = make()
        for _ in range(4):
            director.handle(msg("hi", user="Same"))
        self.assertEqual(len(director.chatters), 1)

    def test_milestones_can_be_switched_off_and_the_test_box_does_not_count(self):
        director, clock, said, _ = make(react_milestones=False)
        for number in range(60):
            director.handle(msg("hi", user="V%d" % number))
        self.assertEqual(said, [])
        director, clock, said, _ = make()
        for number in range(60):
            director.handle(msg("hi", user="V%d" % number), test=True)
        self.assertEqual(director.chat_messages, 0)


class FakeSource:
    def __init__(self, *args):
        self.args = args

    def start(self): pass
    def stop(self): pass


class BridgeDelivery(unittest.TestCase):
    def test_the_bridge_gives_events_to_react_and_messages_to_handle(self):
        director, clock, said, _ = make()
        bridge = ChatBridge(director.settings, director, source_factory=FakeSource, youtube_factory=FakeSource)
        bridge.submit(events.StreamEvent("sub", "Gav"))
        bridge.submit(msg("!lights"))
        import threading
        bridge.start()
        for _ in range(50):
            if said and director.log:
                break
            threading.Event().wait(0.1)
        bridge.stop()
        self.assertEqual([k for k, _ in said], ["StreamEvent_Sub", "StreamChat_Action"])      # the event, then the chat command


class TheWords(unittest.TestCase):
    """Her lines are in voicepacks/default/streaming.json. Every pool must exist and only use values she is given."""
    ALLOWED = {"user", "amount", "months", "viewers", "streak", "count", "people", "messages", "platform"}
    LINES = json.loads((Path(__file__).resolve().parent.parent / "voicepacks" / "default" / "streaming.json").read_text(encoding="utf-8"))

    def test_every_kind_has_lines(self):
        for pool in events.KINDS.values():
            self.assertGreaterEqual(len(self.LINES.get(pool, [])), 3, pool)
        for pool in ("StreamEvent_Gift_Big", "StreamEvent_Raid_Big", "StreamEvent_Resub_Long"):
            self.assertTrue(self.LINES.get(pool), pool)

    def test_lines_only_use_known_values_and_read_out_no_money(self):
        for key, lines in self.LINES.items():
            if not key.startswith("StreamEvent_"):
                continue
            for text in lines:
                for name in re.findall(r"{(\w+)}", text):
                    self.assertIn(name, self.ALLOWED, text)
                self.assertNotRegex(text, r"[$£€]")
                self.assertNotIn("Payden", text)

    def test_lines_that_need_a_user_have_one_when_formatted(self):
        for key, lines in self.LINES.items():
            if key.startswith("StreamEvent_") and not key.startswith(("StreamEvent_Chat",)):
                for text in lines:
                    self.assertIn("{user}", text, text)


if __name__ == "__main__":
    unittest.main()
