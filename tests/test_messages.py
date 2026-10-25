"""Incoming chat read aloud when nothing else is happening."""

import json
import unittest
from pathlib import Path

from core.event_bus import Event, EventBus
from journal.game_state import GameState
from personality.messages import MAX_WAITING, STALE_SECONDS, MessageReader, tidy, tidy_name
from tests.test_phase6b import dialogue, make_settings


class Speech:
    def __init__(self):
        self.said, self.busy = [], False

    def say(self, text=None, priority="normal", event_name="", **kw):
        self.said.append(text)
        return True

    def is_busy(self):
        return self.busy


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def msg(text="Hello there", sender="CMDR Nyx", channel="wing", **extra):
    data = {"From": sender, "Message": text, "Channel": channel}
    data.update(extra)
    return Event("ReceiveText", data, "low")


class Reader(unittest.TestCase):
    def build(self, **values):
        values.setdefault("messages__channels", "all")                   # the other tests use wing and local chat
        self.settings = make_settings(**values)
        self.speech, self.state, self.clock = Speech(), GameState(), Clock()
        self.state.status_flags = 0
        self.r = MessageReader(EventBus(), self.speech, dialogue(), self.settings, lambda: self.state, clock=self.clock)
        return self.r

    def test_reads_a_message_when_calm(self):
        self.build()
        self.r.on_event(msg("Fancy a trip to Colonia?"))
        self.assertTrue(self.r.tick())
        self.assertIn("Fancy a trip to Colonia?", self.speech.said[0])
        self.assertIn("Nyx", self.speech.said[0])
        self.assertNotIn("CMDR", self.speech.said[0])
        self.assertFalse(self.r.tick())                      # nothing left

    def test_waits_while_she_is_talking(self):
        self.build()
        self.speech.busy = True
        self.r.on_event(msg())
        self.assertFalse(self.r.tick())
        self.assertEqual(self.speech.said, [])
        self.speech.busy = False
        self.assertTrue(self.r.tick())

    def test_waits_in_danger_and_after_a_warning(self):
        self.build()
        self.r.on_event(msg())
        self.state.status_flags = 1 << 22                    # in danger
        self.assertFalse(self.r.tick())
        self.state.status_flags = 0
        self.r.on_event(Event("Warning", {}, "critical"))
        self.assertFalse(self.r.tick())
        self.clock.now += 31
        self.assertTrue(self.r.tick())

    def test_waits_with_hardpoints_out(self):
        self.build()
        self.r.on_event(msg())
        self.state.status_flags = 1 << 6
        self.assertFalse(self.r.tick())

    def test_old_messages_are_dropped_and_queue_is_short(self):
        self.build()
        self.r.on_event(msg("old"))
        self.clock.now += STALE_SECONDS + 1
        self.assertFalse(self.r.tick())
        for n in range(MAX_WAITING + 3):
            self.r.on_event(msg("m%d" % n))
        self.assertEqual(len(self.r.queue), MAX_WAITING)

    def test_npc_off_by_default_and_unknown_channels_ignored(self):
        self.build()
        self.r.on_event(msg(channel="npc", sender="Pirate"))
        self.r.on_event(msg(channel="mystery"))
        self.assertEqual(len(self.r.queue), 0)
        self.build(messages__npc=True)
        self.r.on_event(msg(channel="npc", sender="Pirate"))
        self.assertEqual(len(self.r.queue), 1)

    def test_direct_messages_only_is_the_default(self):
        self.build(messages__channels="direct")
        for channel in ("local", "starsystem", "wing", "squadron", "friend", "voicechat"):
            self.r.on_event(msg(channel=channel))
        self.assertEqual(len(self.r.queue), 0)
        self.r.on_event(msg(channel="player"))
        self.assertEqual(len(self.r.queue), 1)

    def test_direct_plus_reads_friends_wing_and_squadron_but_not_local(self):
        self.build(messages__channels="direct_plus")
        for channel in ("local", "starsystem"):
            self.r.on_event(msg(channel=channel))
        self.assertEqual(len(self.r.queue), 0)
        for channel in ("player", "friend", "wing", "squadron"):
            self.r.on_event(msg(channel=channel))
        self.assertEqual(len(self.r.queue), 4)

    def test_the_real_default_is_direct(self):
        from core.settings import DEFAULTS
        self.assertEqual(DEFAULTS["messages"]["channels"], "direct")

    def test_switch_off(self):
        self.build(messages__read=False)
        self.r.on_event(msg())
        self.assertFalse(self.r.tick())
        self.assertEqual(self.speech.said, [])

    def test_localised_text_preferred_and_cleaned(self):
        self.build()
        self.r.on_event(msg("$npc_msg;", sender="$x;", Message_Localised="Look at http://example.com now <b>ok</b>",
                            From_Localised="CMDR Bob"))
        self.r.tick()
        self.assertIn("a link", self.speech.said[0])
        self.assertNotIn("http", self.speech.said[0])
        self.assertNotIn("<b>", self.speech.said[0])
        self.assertIn("Bob", self.speech.said[0])

    def test_no_name_still_reads(self):
        self.build()
        self.r.on_event(msg("hi", sender=""))
        self.assertTrue(self.r.tick())
        self.assertIn("hi", self.speech.said[0])

    def test_tidy(self):
        self.assertEqual(tidy_name("CMDR Nyx"), "Nyx")
        self.assertLessEqual(len(tidy("word " * 200)), 230)


class Lines(unittest.TestCase):
    def test_lines_are_clean(self):
        data = json.loads(Path("voicepacks/default/messages.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertIn("{message}", line)
                self.assertFalse([b for b in banned if b in line.lower()], line)

    def test_event_is_registered(self):
        from events.registry import load_registry
        self.assertIn("ReceiveText", load_registry())
