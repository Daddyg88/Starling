"""The hands-free galaxy map macro for neutron waypoints."""

import tempfile
import unittest
from pathlib import Path

from control.binds import Keystroke
from control.catalog import PLOT_MACRO, by_id
from control.macros import actions_in, parse_macro
from control.matcher import Matcher
from control.runner import CommandRunner
from core.event_bus import EventBus
from journal.game_state import GameState
from navigation.route import AUTO_PLOT_DELAY_SECONDS, BOOST_PLOT_DELAY_SECONDS, RouteFollower
from navigation.voice import RouteVoice
from tests.test_commands import FakeBook, FakeSpeech
from tests.test_neutron import FakeSpansh, Narr, ROUTE
from tests.test_phase6b import dialogue, make_settings

TABLE = {"GalaxyMapOpen": (Keystroke("Key_G"), ""), "UI_Up": (Keystroke("Key_U"), ""), "UI_Select": (Keystroke("Key_S"), ""),
         "UI_Down": (Keystroke("Key_D"), ""), "UI_Back": (Keystroke("Key_B"), ""), "CamZoomIn": (Keystroke("Key_Z"), "")}


class Recorder:
    def __init__(self):
        self.events, self.require_game = [], True

    def send(self, keystroke, hold=None):
        self.events.append((keystroke.describe(), hold))
        return ""


class MacroSteps(unittest.TestCase):
    def test_new_steps_parse(self):
        steps = parse_macro(["paste", "enter", "hold UI_Select 1.5", "wait 1", "UI_Up x2"])
        self.assertEqual(steps, [("literal", "paste"), ("literal", "enter"), ("hold", "UI_Select", 1.5),
                                 ("wait", 1.0), ("press", "UI_Up", 2)])
        self.assertEqual(actions_in(steps), ["UI_Select", "UI_Up"])

    def test_bad_hold_is_refused(self):
        for bad in ("hold", "hold UI_Select", "hold UI_Select abc", "hold UI_Select 1 2"):
            with self.assertRaises(ValueError):
                parse_macro([bad])

    def test_hold_is_capped(self):
        self.assertEqual(parse_macro(["hold UI_Select 99"])[0][2], 5.0)

    def test_default_macro_is_valid(self):
        steps = parse_macro(PLOT_MACRO)
        self.assertEqual(steps[0][1], "GalaxyMapOpen")
        self.assertEqual(steps[-1][1], "UI_Back")
        self.assertIn(("literal", "paste"), steps)
        self.assertNotIn(("literal", "enter"), steps)          # the recording shows Down + Select, not Enter
        self.assertIn(("hold", "UI_Select", 1.2), steps)
        self.assertEqual(set(actions_in(steps)), {"GalaxyMapOpen", "UI_Up", "UI_Select", "UI_Back", "CamZoomIn"})

    def test_supercharge_waits_three_seconds(self):
        self.assertEqual(AUTO_PLOT_DELAY_SECONDS, 3.0)


class Phrases(unittest.TestCase):
    def test_phrases(self):
        m = Matcher()
        self.assertEqual(m.conflicts, [])
        for text in ("plot the next waypoint", "set the next waypoint", "plot next neutron star", "plot the waypoint",
                     "put in the next waypoint"):
            match = m.match(text)
            self.assertIsNotNone(match, text)
            self.assertEqual(match.command.id, "plot_waypoint", text)

    def test_route_questions_still_go_to_the_route_code(self):
        f = RouteFollowerHolder.build()
        v = f["voice"]
        self.assertIsNone(v.try_handle("plot the next waypoint"))
        self.assertIsNone(v.try_handle("set the route to the next waypoint"))
        self.assertIn("Neutron A", v.try_handle("where is the next waypoint"))


class RouteFollowerHolder:
    @staticmethod
    def build(**values):
        settings = make_settings(**values)
        state = GameState()
        state.system, state.max_jump_range = "Sol", 60.0
        narr, copied, later = Narr(), [], []
        follower = RouteFollower(EventBus(), settings, narr, lambda: state, save_path=Path(tempfile.mkdtemp()) / "r.json",
                                 copier=lambda t: copied.append(t) or True, schedule=lambda s, fn: later.append((s, fn)))
        follower.attach()
        voice = RouteVoice(follower, FakeSpansh(), narr, settings, lambda: state, spawn=lambda fn: fn())
        follower.set_route(ROUTE, "Colonia", here="Sol")
        return dict(settings=settings, state=state, narr=narr, copied=copied, later=later, follower=follower, voice=voice)


class RunMacro(unittest.TestCase):
    def runner(self, voice=None, **values):
        self.parts = RouteFollowerHolder.build(**values)
        self.rec = Recorder()
        hooks = {"plot_waypoint": self.parts["voice"].prepare_plot}
        return CommandRunner(EventBus(), FakeSpeech(), dialogue(), self.parts["settings"], book=FakeBook(TABLE),
                             sender=self.rec, sleep=lambda s: None, macro_hooks=hooks)

    def test_full_sequence(self):
        outcome = self.runner().run_text("plot the next waypoint")[0]
        self.assertEqual(outcome.status, "done")
        pressed = [e[0] for e in self.rec.events]
        g, u, sel = (Keystroke(k).describe() for k in ("Key_G", "Key_U", "Key_S"))
        d, b = (Keystroke(k).describe() for k in ("Key_D", "Key_B"))
        # map, up to the search box, click in, paste, select the result, (hold select), back, back
        x = Keystroke("Key_Z").describe()
        self.assertEqual(pressed, [g, u, sel, "Left Control + V", sel, x, sel, b, b])
        self.assertEqual([h for _, h in self.rec.events if h], [0.2, 1.2])  # zoom in briefly, then hold select
        self.assertEqual(self.parts["copied"][-1], "Neutron A")             # the clipboard was filled first

    def test_open_galaxy_map_is_not_toggled_closed(self):
        r = self.runner()
        r.state_provider = lambda: type("S", (), {"status_seen": True, "gui_focus": 6, "status_flags": 0, "status_flags2": 0})()
        outcome = r.run_text("plot the next waypoint")[0]
        self.assertEqual(outcome.status, "done")
        pressed = [e[0] for e in self.rec.events]
        g, u = (Keystroke(k).describe() for k in ("Key_G", "Key_U"))
        self.assertNotIn(g, pressed)                     # the map key was never pressed (it would have closed the map)
        self.assertEqual(pressed[0], u)

    def test_no_route_means_no_key_presses(self):
        r = self.runner()
        self.parts["follower"].clear()
        outcome = r.run_text("plot the next waypoint")[0]
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(self.rec.events, [])
        self.assertIn("no route", outcome.detail.lower())

    def test_needs_clipboard_on(self):
        r = self.runner(neutron__clipboard=False)
        outcome = r.run_text("plot the next waypoint")[0]
        self.assertEqual((outcome.status, self.rec.events), ("failed", []))

    def test_missing_key_is_explained_before_anything_is_pressed(self):
        r = self.runner()
        r.book = FakeBook({"GalaxyMapOpen": TABLE["GalaxyMapOpen"]})
        outcome = r.run_text("plot the next waypoint")[0]
        self.assertIn("UI_", outcome.detail)
        self.assertEqual(self.rec.events, [])

    def test_your_own_steps_win(self):
        r = self.runner(macros__plot_waypoint=["GalaxyMapOpen", "paste", "GalaxyMapOpen"])
        r.run_text("plot the next waypoint")
        self.assertEqual(len(self.rec.events), 3)


class AutoPlot(unittest.TestCase):
    def setUp(self):
        self.p = RouteFollowerHolder.build(neutron__auto_plot=True)
        self.ran = []
        self.p["follower"].auto_plot = lambda: self.ran.append(1)
        self.bus = self.p["follower"].bus

    def fire(self):
        for _, fn in self.p["later"]:
            fn()
        self.p["later"].clear()

    def test_after_the_supercharge(self):
        self.bus.publish("JetConeBoost", {"BoostValue": 4})
        self.assertEqual(self.p["later"][0][0], BOOST_PLOT_DELAY_SECONDS)
        self.assertEqual(BOOST_PLOT_DELAY_SECONDS, 4.0)
        self.fire()
        self.assertEqual(len(self.ran), 1)
        self.bus.publish("JetConeBoost", {"BoostValue": 4})              # a second boost on the same waypoint
        self.fire()
        self.assertEqual(len(self.ran), 1)

    def test_again_after_the_next_waypoint(self):
        self.bus.publish("JetConeBoost", {})
        self.bus.publish("FSDJump", {"StarSystem": "Neutron A"})
        self.bus.publish("JetConeBoost", {})
        self.fire()
        self.assertEqual(len(self.ran), 2)

    def test_fuel_stop_plots_straight_away(self):
        f = self.p["follower"]
        f.waypoints[1] = dict(f.waypoints[1], neutron=False)
        f._auto_for = None
        self.bus.publish("FSDJump", {"StarSystem": "Neutron A"})
        self.fire()
        self.assertEqual(len(self.ran), 1)

    def test_on_by_default(self):
        self.assertTrue(RouteFollowerHolder.build()["settings"].get("neutron.auto_plot"))

    def test_off_when_switched_off_and_when_unsafe(self):
        off = RouteFollowerHolder.build(neutron__auto_plot=False)
        off["follower"].auto_plot = lambda: self.ran.append(1)
        off["follower"].bus.publish("JetConeBoost", {})
        self.assertEqual(off["later"], [])
        self.p["state"].status_flags = 1 << 22                            # in danger
        self.bus.publish("JetConeBoost", {})
        self.assertEqual(self.p["later"], [])
        self.p["state"].status_flags = (1 << 6) | (1 << 17)               # weapons out and FSD charging are fine
        self.bus.publish("JetConeBoost", {})
        self.assertEqual(len(self.p["later"]), 1)
        self.p["later"].clear()
        self.p["follower"]._auto_for = None
        self.p["state"].status_flags = 0
        self.bus.publish("JetConeBoost", {})
        self.assertEqual(len(self.p["later"]), 1)

    def test_route_ready_starts_it(self):
        self.p["follower"]._auto_for = None
        self.assertTrue(self.p["follower"].maybe_auto_plot())
        self.assertEqual(self.p["later"][-1][0], AUTO_PLOT_DELAY_SECONDS)

    def test_plotting_a_route_by_voice_runs_the_macro_for_the_first_waypoint(self):
        self.p["follower"]._auto_for = None
        self.p["voice"].plot("Colonia")                                   # spawn runs at once in the tests
        self.fire()
        self.assertEqual(len(self.ran), 1)

    def test_nothing_connected_does_nothing(self):
        self.p["follower"].auto_plot = None
        self.p["follower"]._auto_for = None
        self.assertFalse(self.p["follower"].maybe_auto_plot())


class AppWiring(unittest.TestCase):
    def test_the_app_connects_the_macro_to_the_follower(self):
        from unittest import mock
        from core.app import App

        class FakeSender:
            require_game = True

            def send(self, *a, **k):
                return ""
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            app = App(settings_path=folder / "s.json", database_path=folder / "t.db", logs_dir=folder / "logs")
            app.start()
            try:
                with mock.patch("control.sender.KeySender", FakeSender):
                    self.assertIsNotNone(app.ensure_commands())
                self.assertIsNotNone(app.route_follower)
                self.assertIsNotNone(app.route_follower.auto_plot)
                # the macro must really call the clipboard step first (it was never wired up before 0.23.3)
                hook = app.commands.macro_hooks.get("plot_waypoint")
                self.assertIsNotNone(hook)
                copied = []
                app.route_follower.copier = lambda text: copied.append(text) or True
                app.route_voice.set_target("Wregoe JU-E c25-18")
                self.assertEqual(hook(), (True, ""))
                self.assertEqual(copied, ["Wregoe JU-E c25-18"])
            finally:
                app.stop()


if __name__ == "__main__":
    unittest.main()


class NavigationButtonTests(unittest.TestCase):
    """The Navigation page buttons call these App methods (the page itself needs a real screen to test)."""

    def make(self):
        from core.app import App
        app = App.__new__(App)
        calls = []

        class Voice:
            def enabled(self_inner):
                return True

            def plot(self_inner, text):
                calls.append(("plot", text))
                return "Plotting a neutron route to " + text

            def try_handle(self_inner, text):
                calls.append(("handle", text))
                return "Route cancelled."
        app.ensure_route = lambda: Voice()
        return app, calls

    def test_plot_uses_typed_destination_or_the_saved_one(self):
        app, calls = self.make()
        app.plot_route_now("Colonia")
        app.plot_route_now("")
        self.assertEqual(calls, [("plot", "Colonia"), ("plot", "my destination")])

    def test_clear(self):
        app, calls = self.make()
        self.assertEqual(app.clear_route_now(), "Route cancelled.")

    def test_next_waypoint_runs_the_macro_after_the_delay(self):
        from core.app import App
        import threading
        app = App.__new__(App)
        done = threading.Event()
        waits = []
        ran = []

        class Runner:
            def run_text(self_inner, text, speak_unknown=True):
                ran.append(text)
                done.set()
        app.ensure_commands = lambda: Runner()
        message = app.plot_next_now(delay=4, sleep=waits.append)
        self.assertTrue(done.wait(2))
        self.assertEqual(waits, [4])
        self.assertEqual(ran, ["plot the next waypoint"])
        self.assertIn("4 seconds", message)


class AutoLaunchTests(unittest.TestCase):
    def test_launch_phrases_and_scoop_words(self):
        from control.matcher import Matcher
        m = Matcher()
        for text in ("launch", "auto launch", "launch from the station", "undock"):
            self.assertEqual(m.match(text).command.id, "auto_launch", text)
        self.assertEqual(m.match("launch the nomad").command.id, "deploy_nomad")
        self.assertEqual((m.match("lower the cargo scoop").command.id, m.match("lower the cargo scoop").intent), ("scoop", "on"))
        self.assertEqual(m.match("raise the cargo scoop").intent, "off")
        self.assertEqual(m.match("cargo scoop up").intent, "off")

    def test_launch_only_while_docked(self):
        from types import SimpleNamespace
        from core.app import App
        check = App._launch_check
        fake = lambda **kw: SimpleNamespace(state=SimpleNamespace(**kw))
        self.assertTrue(check(fake(status_seen=True, status_flags=1))[0])
        self.assertFalse(check(fake(status_seen=True, status_flags=16))[0])
        self.assertTrue(check(fake(status_seen=False, status_flags=0))[0])


class VoidCompassNoClashTests(unittest.TestCase):
    """Saying the name of a Void Compass overlay must never press a ship control, and ship phrases must never switch an overlay."""

    def test_overlay_phrases_never_hit_ship_commands(self):
        from control.catalog import CATALOG
        from control.matcher import Matcher
        from control.vc_overlays import OVERLAYS
        overlay_ids = {c.id for c in CATALOG if c.service}
        m = Matcher()
        for _oid, _label, names, needs_word in OVERLAYS:
            if needs_word:
                names = [n + " overlay" for n in names]          # the bare word (cargo, navigation...) belongs to the ship
            for name in names:
                for verb in ("show", "hide", "turn on", "turn off"):
                    found = m.match("%s the %s" % (verb, name))
                    if found is not None:
                        self.assertIn(found.command.id, overlay_ids, "%s the %s" % (verb, name))

    def test_ship_phrases_never_hit_overlays(self):
        from control.catalog import CATALOG
        from control.matcher import Matcher
        overlay_ids = {c.id for c in CATALOG if c.service}
        m = Matcher()
        for text in ("lower the landing gear", "raise landing gear", "cargo scoop up", "deploy hardpoints", "lights on",
                     "open the galaxy map", "open the left panel", "show navigation", "open comms", "flight assist off"):
            found = m.match(text)
            self.assertIsNotNone(found, text)
            self.assertNotIn(found.command.id, overlay_ids, text)
