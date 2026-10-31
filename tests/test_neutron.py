"""Neutron route plotter: Spansh client, route following, and the voice commands (all with pretend network)."""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from control.runner import CommandRunner
from core.event_bus import EventBus
from journal.game_state import GameState
from navigation.route import RouteFollower
from navigation.spansh import Spansh, SpanshError
from navigation.voice import Narrator, RouteVoice, clean
from tests.test_commands import FakeBook, FakeSender, FakeSpeech
from tests.test_phase6b import dialogue, make_settings

ROUTE = [
    {"system": "Sol", "neutron": False, "jumps": 0, "distance_left": 100},
    {"system": "Neutron A", "neutron": True, "jumps": 3, "distance_left": 70},
    {"system": "Neutron B", "neutron": True, "jumps": 2, "distance_left": 30},
    {"system": "Colonia", "neutron": False, "jumps": 4, "distance_left": 0},
]


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNet:
    """Answers like Spansh: a job, two 'queued' polls, then the result."""
    def __init__(self, systems=("Colonia",), polls=2, fail=None):
        self.calls, self.systems, self.polls, self.fail = [], systems, polls, fail

    def __call__(self, request, timeout=None):
        url, data = request.full_url, request.data
        self.calls.append((url, data))
        if self.fail:
            raise self.fail
        if "/search/systems" in url:
            return Reply(json.dumps({"results": [{"name": n} for n in self.systems]}).encode())
        if url.endswith("/route"):
            return Reply(b'{"job": "abc-123", "status": "queued"}')
        if "/results/" in url:
            if self.polls > 0:
                self.polls -= 1
                return Reply(b'{"status": "queued"}')
            rows = [{"system": w["system"], "neutron_star": w["neutron"], "jumps": w["jumps"],
                     "distance_left": w["distance_left"]} for w in ROUTE]
            return Reply(json.dumps({"status": "ok", "result": {"system_jumps": rows}}).encode())
        raise AssertionError(url)


class SpanshTests(unittest.TestCase):
    def test_route_steps_and_form(self):
        net = FakeNet()
        route = Spansh(opener=net, sleep=lambda s: None).neutron_route("Sol", "Colonia", 55.5, 60, 4)
        self.assertEqual([w["system"] for w in route], ["Sol", "Neutron A", "Neutron B", "Colonia"])
        self.assertTrue(route[1]["neutron"] and not route[0]["neutron"])
        sent = net.calls[0][1].decode()
        for part in ("from=Sol", "to=Colonia", "range=55.50", "efficiency=60", "supercharge_multiplier=4"):
            self.assertIn(part, sent)
        self.assertEqual(sum("/results/" in c[0] for c in net.calls), 3)      # two queued, then ok

    def test_supercharge_six(self):
        net = FakeNet()
        Spansh(opener=net, sleep=lambda s: None).neutron_route("Sol", "Colonia", 50, 60, 6)
        self.assertIn("supercharge_multiplier=6", net.calls[0][1].decode())

    def test_find_system_exact_and_closest(self):
        self.assertEqual(Spansh(opener=FakeNet(("Colonial", "Colonia"))).find_system("colonia"), "Colonia")
        self.assertEqual(Spansh(opener=FakeNet(("Beagle Point",))).find_system("beagle pint"), "Beagle Point")

    def test_find_system_nothing_close(self):
        with self.assertRaises(SpanshError):
            Spansh(opener=FakeNet(("Zzzzzz",))).find_system("colonia")
        with self.assertRaises(SpanshError):
            Spansh(opener=FakeNet(())).find_system("colonia")

    def test_offline_and_http_errors(self):
        with self.assertRaises(SpanshError) as caught:
            Spansh(opener=FakeNet(fail=urllib.error.URLError("down"))).find_system("Sol")
        self.assertIn("internet", str(caught.exception))
        body = io.BytesIO(b'{"error": "Range too short"}')
        error = urllib.error.HTTPError("u", 400, "bad", {}, body)
        with self.assertRaises(SpanshError) as caught:
            Spansh(opener=FakeNet(fail=error)).neutron_route("Sol", "X", 5)
        self.assertIn("Range too short", str(caught.exception))

    def test_timeout(self):
        net = FakeNet(polls=999)
        now = [0.0]

        def clock():
            now[0] += 5
            return now[0]
        with self.assertRaises(SpanshError):
            Spansh(opener=net, sleep=lambda s: None, clock=clock).neutron_route("Sol", "X", 50, max_wait=20)


class Narr:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, fields or {}))


class FollowerTests(unittest.TestCase):
    def build(self, **values):
        self.tmp = Path(tempfile.mkdtemp()) / "route.json"
        self.settings = make_settings(**values)
        self.copied, self.later = [], []
        self.narr = Narr()
        self.bus = EventBus()
        self.f = RouteFollower(self.bus, self.settings, self.narr, save_path=self.tmp,
                               copier=lambda t: self.copied.append(t) or True,
                               schedule=lambda s, fn: self.later.append(fn))
        self.f.attach()
        return self.f

    def jump(self, system):
        self.bus.publish("FSDJump", {"StarSystem": system})

    def test_start_skips_current_system(self):
        f = self.build()
        f.set_route(ROUTE, "Colonia", here="Sol")
        self.assertEqual(f.next_waypoint()["system"], "Neutron A")
        self.assertEqual(f.jumps_left, 3)
        self.assertEqual((f.stops_left(), f.total_jumps_left()), (2, 9))

    def test_following_the_route(self):
        f = self.build()
        f.set_route(ROUTE, "Colonia", here="Sol")
        self.jump("Random 1")
        self.jump("Random 2")
        self.assertEqual((f.jumps_left, self.copied), (1, []))
        self.jump("Neutron A")
        self.assertEqual(self.copied, ["Neutron B"])
        self.assertEqual(f.jumps_left, 2)
        self.later[-1]()
        self.assertEqual(self.narr.said[-1][0], "RouteNeutronNext")
        self.assertEqual(self.narr.said[-1][1]["next"], "Neutron B")
        self.jump("Neutron B")
        self.assertEqual(self.copied[-1], "Colonia")
        self.jump("Colonia")
        self.assertFalse(f.active)
        self.assertEqual(self.narr.said[-1][0], "RouteArrived")

    def test_skipping_a_waypoint_still_works(self):
        f = self.build()
        f.set_route(ROUTE, "Colonia", here="Sol")
        self.jump("Neutron B")
        self.assertEqual(f.next_waypoint()["system"], "Colonia")

    def test_clipboard_and_announce_switches(self):
        f = self.build(neutron__clipboard=False, neutron__announce=False)
        f.set_route(ROUTE, "Colonia", here="Sol")
        self.jump("Neutron A")
        self.later[-1]()
        self.assertEqual((self.copied, self.narr.said), ([], []))

    def test_remembered_after_restart(self):
        f = self.build()
        f.set_route(ROUTE, "Colonia", here="Sol")
        self.jump("Neutron A")
        again = RouteFollower(EventBus(), self.settings, None, save_path=self.tmp, copier=lambda t: True)
        self.assertEqual((again.destination, again.next_waypoint()["system"]), ("Colonia", "Neutron B"))

    def test_clear(self):
        f = self.build()
        f.set_route(ROUTE, "Colonia", here="Sol")
        f.clear()
        self.assertFalse(f.active)
        self.assertEqual(RouteFollower(EventBus(), self.settings, None, save_path=self.tmp).waypoints, [])

    def test_ignores_jumps_with_no_route(self):
        self.build()
        self.jump("Anywhere")
        self.assertEqual(self.narr.said, [])


class FakeSpansh:
    def __init__(self, error=None):
        self.error, self.asked = error, []

    def find_system(self, name):
        self.asked.append(("find", name))
        if self.error:
            raise self.error
        return {"Sagittarius A*": "Sagittarius A*"}.get(name, name)

    def neutron_route(self, start, dest, rng, eff, sc):
        self.asked.append(("route", start, dest, rng, eff, sc))
        return [dict(w) for w in ROUTE]


class VoiceTests(unittest.TestCase):
    def build(self, range_ly=60.0, system="Sol", spansh=None, **values):
        self.settings = make_settings(**values)
        self.state = GameState()
        self.state.system, self.state.max_jump_range = system, range_ly
        self.narr = Narr()
        self.copied = []
        self.f = RouteFollower(EventBus(), self.settings, self.narr, save_path=Path(tempfile.mkdtemp()) / "r.json",
                               copier=lambda t: self.copied.append(t) or True, schedule=lambda s, fn: None)
        self.spansh = spansh or FakeSpansh()
        self.v = RouteVoice(self.f, self.spansh, self.narr, self.settings, lambda: self.state, spawn=lambda fn: fn())
        return self.v

    def keys(self):
        return [k for k, _ in self.narr.said]

    def test_plot_phrases(self):
        for text, dest in [
            ("plot a neutron route to Colonia", "Colonia"),
            ("Starling, plot me a neutron route to Beagle Point please", "Beagle Point"),
            ("work out a route to Sagittarius A star", "Sagittarius A*"),
            ("set a neutron course to the bubble", "Sol"),
            ("find a neutron route to colonia using neutron stars", "Colonia"),
            ("plot neutron route to HIP 12345", "HIP 12345"),
        ]:
            self.build()
            self.assertIsNotNone(self.v.try_handle(text), text)
            self.assertIn(("find", dest), self.spansh.asked, text)

    def test_full_plot_uses_range_margin_and_copies_first_waypoint(self):
        self.build(60.0)
        self.v.try_handle("plot a neutron route to colonia")
        route_call = [c for c in self.spansh.asked if c[0] == "route"][0]
        self.assertEqual(route_call[1:4], ("Sol", "Colonia", 54.0))     # 60 x 0.9
        self.assertEqual(self.copied, ["Neutron A"])
        self.assertEqual(self.keys(), ["RoutePlotting", "RouteReady"])
        self.assertEqual(self.narr.said[-1][1]["stops"], 2)

    def test_manual_range_wins(self):
        self.build(60.0, neutron__jump_range="48.5")
        self.v.try_handle("plot a neutron route to colonia")
        self.assertEqual([c for c in self.spansh.asked if c[0] == "route"][0][3], 48.5)

    def test_my_destination(self):
        self.build(neutron__destination="Colonia")
        self.v.try_handle("plot a neutron route to my destination")
        self.assertIn(("find", "Colonia"), self.spansh.asked)
        self.build()
        self.v.try_handle("plot a neutron route to my destination")
        self.assertEqual(self.keys(), ["RouteNoDestination"])

    def test_own_favourites(self):
        self.build(neutron__favourites={"home": "Shinrarta Dezhra"})
        self.v.try_handle("plot a neutron route to home")
        self.assertIn(("find", "Shinrarta Dezhra"), self.spansh.asked)

    def test_missing_pieces_are_explained(self):
        self.build(range_ly=None)
        self.v.try_handle("plot a neutron route to colonia")
        self.assertEqual(self.keys(), ["RoutePlotting", "RouteNoRange"])
        self.build(system=None)
        self.v.try_handle("plot a neutron route to colonia")
        self.assertEqual(self.keys(), ["RoutePlotting", "RouteNoLocation"])

    def test_spansh_trouble_is_spoken(self):
        self.build(spansh=FakeSpansh(SpanshError("I can't reach Spansh.")))
        self.v.try_handle("plot a neutron route to colonia")
        self.assertEqual(self.keys()[-1], "RouteFailed")
        self.assertIn("Spansh", self.narr.said[-1][1]["reason"])
        self.assertFalse(self.v._busy)

    def test_next_status_cancel_replot(self):
        self.build()
        self.v.try_handle("plot a neutron route to colonia")
        self.copied.clear()
        self.assertIn("Neutron A", self.v.try_handle("where's the next waypoint"))
        self.assertEqual(self.copied, ["Neutron A"])
        self.assertIn("jumps", self.v.try_handle("how far is left on the route"))
        self.v.try_handle("replot the route")
        self.assertEqual(self.spansh.asked[-1][0], "route")
        self.assertEqual(self.v.try_handle("cancel the route"), "Route cancelled.")
        self.assertFalse(self.f.active)
        self.assertEqual(self.v.try_handle("cancel the route"), "There was no route.")

    def test_other_sentences_are_not_taken(self):
        self.build()
        for text in ("lower the landing gear", "open the galaxy map", "plot a route", "show the cargo overlay",
                     "what's next on the menu", "how far is the star"):
            self.assertIsNone(self.v.try_handle(text), text)

    def test_switched_off(self):
        self.build(neutron__enabled=False)
        self.assertIsNone(self.v.try_handle("plot a neutron route to colonia"))

    def test_clean(self):
        self.assertEqual(clean("Sagittarius A*, please!"), "sagittarius a star")


class RunnerHookTests(unittest.TestCase):
    def test_runner_hands_route_sentences_to_the_plotter(self):
        v = VoiceTests()
        v.build()
        speech = FakeSpeech()
        runner = CommandRunner(EventBus(), speech, dialogue(), v.settings, book=FakeBook(), sender=FakeSender(),
                               sleep=lambda s: None, route=v.v)
        outcome = runner.run_text("plot a neutron route to colonia")[0]
        self.assertEqual(outcome.status, "route")
        self.assertEqual(v.f.next_waypoint()["system"], "Neutron A")
        self.assertEqual(speech.said, [])                                   # the narrator (fake) spoke, not the runner
        self.assertEqual(runner.run_text("lower the landing gear")[0].command.id, "gear")


class NarratorTests(unittest.TestCase):
    def test_every_route_line_exists_for_every_mood_and_formats(self):
        pool = dialogue()
        keys = ["RoutePlotting", "RouteReady", "RouteNeutronNext", "RouteNext", "RouteNextAgain", "RouteStatus",
                "RouteArrived", "RouteCancelled", "RouteNone", "RouteNoDestination", "RouteNoLocation",
                "RouteNoRange", "RouteFailed"]
        fields = dict(destination="Colonia", next="Neutron A", jumps=3, stops=2, left=9, clip=" On clipboard.", reason="why", count="3 waypoints to go.")
        for key in keys:
            for mood in ("Close", "Friendly", "Neutral", "Sarcastic", "Frustrated"):
                self.assertTrue(pool.pool(key, mood, False, False), (key, mood))
                for line in pool.pool(key, mood, False, False):
                    line.text.format(**fields)

    def test_narrator_speaks_with_facts(self):
        speech = FakeSpeech()
        settings = make_settings()
        Narrator(lambda: speech, dialogue(), settings).say("RouteNextAgain", {"next": "Neutron A", "jumps": 3, "clip": ""})
        self.assertIn("Neutron A", speech.said[0]["text"])
        self.assertEqual(speech.said[0]["event_name"], "personality.route")

    def test_loadout_records_jump_range(self):
        from events.loadout import Loadout
        state = GameState()
        Loadout().update_state({"Ship": "anaconda", "MaxJumpRange": 61.25}, state)
        self.assertEqual(state.max_jump_range, 61.25)


if __name__ == "__main__":
    unittest.main()
