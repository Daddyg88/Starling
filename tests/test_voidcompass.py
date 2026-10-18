"""Void Compass overlay voice commands: the matching, the runner, and the HTTP client (no network needed)."""

import io
import json
import unittest
import urllib.error

from control.catalog import CATALOG
from control.matcher import Matcher
from control.runner import CommandRunner
from control.vc_overlays import OVERLAYS
from control.voidcompass import VoidCompass, VoidError
from core.event_bus import EventBus
from tests.test_commands import FakeBook, FakeSender, FakeSpeech
from tests.test_phase6b import dialogue, make_settings


class FakeVoid:
    def __init__(self, enabled=None, hidden=False, error=None):
        self.state = {o[0]: False for o in OVERLAYS}
        self.state.update(enabled or {})
        self.hidden, self.error, self.calls = hidden, error, []

    def overlays(self):
        if self.error:
            raise self.error
        return {"hidden": self.hidden, "overlays": [{"id": k, "enabled": v} for k, v in self.state.items()]}

    def set_enabled(self, overlay_id, enabled):
        if self.error:
            raise self.error
        self.calls.append(("set", overlay_id, enabled))
        self.state[overlay_id] = enabled

    def hide_all(self, hidden):
        if self.error:
            raise self.error
        self.calls.append(("hide_all", hidden))
        self.hidden = hidden


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.matcher = Matcher()

    def test_no_phrase_is_claimed_twice(self):
        self.assertEqual(self.matcher.conflicts, [])

    def test_every_overlay_can_be_shown_and_hidden(self):
        for overlay_id, label, names, needs_word in OVERLAYS:
            for name in names:
                on = self.matcher.match("show the %s overlay" % name)
                off = self.matcher.match("hide the %s overlay" % name)
                self.assertIsNotNone(on, name)
                self.assertEqual((on.command.service, on.intent), (("voidcompass", overlay_id), "on"), name)
                self.assertEqual((off.command.service, off.intent), (("voidcompass", overlay_id), "off"), name)

    def test_natural_sentences(self):
        for text, target, intent in [
            ("turn on the cargo overlay", "cargo", "on"),
            ("switch off the navigation HUD", "navigation", "off"),
            ("toggle the galaxy minimap", "galaxy-minimap", "toggle"),
            ("open the music player", "music-player", "on"),
            ("hide galnet ticker", "galnet-ticker", "off"),
            ("show deep space contacts", "contact-scope", "on"),
            ("close the powerplay overlay", "powerplay", "off"),
        ]:
            match = self.matcher.match(text)
            self.assertIsNotNone(match, text)
            self.assertEqual((match.command.service[1], match.intent), (target, intent), text)

    def test_ship_commands_still_win_when_no_overlay_word(self):
        self.assertEqual(self.matcher.match("open the left panel").command.id, "left_panel")
        self.assertEqual(self.matcher.match("show navigation").command.id, "left_panel")
        self.assertEqual(self.matcher.match("deploy the cargo scoop").command.id, "scoop")

    def test_hide_and_show_everything(self):
        for text in ("hide all overlays", "hide the overlays", "clear the overlays"):
            self.assertEqual(self.matcher.match(text).command.id, "vc_hide_all", text)
        for text in ("show all overlays", "bring back the overlays", "overlays on"):
            self.assertEqual(self.matcher.match(text).command.id, "vc_show_all", text)

    def test_catalog_has_every_overlay(self):
        ids = {c.service[1] for c in CATALOG if c.service}
        self.assertTrue({o[0] for o in OVERLAYS} <= ids)


class RunnerTests(unittest.TestCase):
    def build(self, void=None, **settings):
        self.void = void or FakeVoid()
        self.speech, self.sender = FakeSpeech(), FakeSender()
        self.runner = CommandRunner(EventBus(), self.speech, dialogue(), make_settings(**settings), book=FakeBook(),
                                    sender=self.sender, voidcompass=self.void, sleep=lambda s: None)
        return self.runner

    def run_one(self, text):
        return self.runner.run_text(text)[0]

    def test_show_switches_it_on_without_pressing_any_key(self):
        self.build()
        outcome = self.run_one("show the cargo overlay")
        self.assertEqual(outcome.status, "done")
        self.assertEqual(self.void.calls, [("set", "cargo", True)])
        self.assertEqual(self.sender.pressed, [])

    def test_already_on_is_not_toggled_back(self):
        self.build(FakeVoid({"cargo": True}))
        outcome = self.run_one("show the cargo overlay")
        self.assertEqual(outcome.status, "already")
        self.assertEqual(self.void.calls, [])

    def test_toggle_flips_whatever_it_is(self):
        self.build(FakeVoid({"powerplay": True}))
        self.run_one("toggle the powerplay overlay")
        self.assertEqual(self.void.calls, [("set", "powerplay", False)])

    def test_hide_all_and_show_all(self):
        self.build()
        self.run_one("hide all overlays")
        self.runner._last.clear()
        self.run_one("show all overlays")
        self.assertEqual(self.void.calls, [("hide_all", True), ("hide_all", False)])

    def test_turning_one_on_while_all_hidden_says_so(self):
        self.build(FakeVoid(hidden=True))
        outcome = self.run_one("show the cargo overlay")
        self.assertIn("hidden", outcome.detail)

    def test_void_compass_not_running(self):
        self.build(FakeVoid(error=VoidError("offline")))
        outcome = self.run_one("show the cargo overlay")
        self.assertEqual(outcome.status, "vc_offline")
        self.assertIn("Void Compass", self.speech.said[-1]["text"])

    def test_control_switched_off_in_void_compass(self):
        self.build(FakeVoid(error=VoidError("forbidden")))
        self.assertEqual(self.run_one("hide the cargo overlay").status, "vc_forbidden")

    def test_overlay_unknown_to_this_version(self):
        void = FakeVoid()
        del void.state["cargo"]
        self.build(void)
        self.assertEqual(self.run_one("show the cargo overlay").status, "vc_missing")

    def test_switched_off_in_starling_settings(self):
        self.build(voidcompass__enabled=False)
        outcome = self.run_one("show the cargo overlay")
        self.assertEqual(outcome.status, "vc_disabled")
        self.assertEqual(self.void.calls, [])

    def test_works_when_elite_is_not_in_front(self):
        self.build()
        self.sender.problem = "game_not_active"
        self.assertEqual(self.run_one("show the cargo overlay").status, "done")

    def test_explain_and_binding_report_ignore_them(self):
        self.build()
        self.assertIn("Void Compass", self.runner.explain("show the cargo overlay")[0])
        working, problems = self.runner.binding_report()
        self.assertFalse([p for p in problems if "overlay" in p[0] or p[0] == "the overlays"])


class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ClientTests(unittest.TestCase):
    def client(self, reply=None, error=None):
        self.seen = []

        def opener(request, timeout=None):
            self.seen.append((request.get_method(), request.full_url, request.data))
            if error:
                raise error
            return FakeReply(json.dumps(reply or {}).encode())
        return VoidCompass(port=7380, opener=opener)

    def test_urls_and_bodies(self):
        c = self.client({"overlays": []})
        c.overlays()
        c.set_enabled("cargo", True)
        c.hide_all(True)
        c.hide_all(False)
        self.assertEqual(self.seen[0][:2], ("GET", "http://127.0.0.1:7380/api/v1/overlays"))
        self.assertEqual(self.seen[1][:2], ("POST", "http://127.0.0.1:7380/api/v1/overlays/cargo"))
        self.assertEqual(json.loads(self.seen[1][2]), {"enabled": True})
        self.assertTrue(self.seen[2][1].endswith("/overlays/hide-all"))
        self.assertTrue(self.seen[3][1].endswith("/overlays/show-all"))

    def test_other_port(self):
        self.assertEqual(VoidCompass(port=9000).base, "http://127.0.0.1:9000/api/v1")

    def test_connection_refused_is_offline(self):
        with self.assertRaises(VoidError) as caught:
            self.client(error=urllib.error.URLError("refused")).overlays()
        self.assertEqual(caught.exception.kind, "offline")

    def test_http_errors_become_kinds(self):
        for code, kind in ((403, "forbidden"), (404, "missing"), (409, "conflict"), (503, "offline"), (500, "failed")):
            body = io.BytesIO(json.dumps({"error": {"status": code, "message": "why"}}).encode())
            error = urllib.error.HTTPError("u", code, "m", {}, body)
            with self.assertRaises(VoidError) as caught:
                self.client(error=error).set_enabled("cargo", True)
            self.assertEqual(caught.exception.kind, kind)
            self.assertEqual(caught.exception.message, "why")


if __name__ == "__main__":
    unittest.main()
