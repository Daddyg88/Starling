import json
import tempfile
import unittest
from pathlib import Path

from tests.test_callouts import EmergencyTests
from tests.test_status_reader import make_processor
from journal.status_reader import StatusReader


def lost_voice(**kw):
    v = EmergencyTests().make(**kw)
    v.game_target = lambda: None                    # no destination set anywhere
    v.settings.v["neutron.destination"] = ""
    return v


class LostAndNearestPoi(unittest.TestCase):
    def test_lost_with_no_destination_goes_to_the_nearest_poi(self):
        v = lost_voice(places=[EmergencyTests().place()])
        self.assertEqual(v.try_handle("i'm lost"), "Finding the nearest point of interest.")
        self.assertEqual(v.narrator.said, ["PoiPlotting"])
        self.assertEqual(v.target_override, "Landmark")
        self.assertEqual(v.follower.ran, 1)
        self.assertIsNone(v._emergency)                     # no neutron route afterwards
        self.assertEqual(v.spansh.routes, [])

    def test_emergency_protocol_with_no_destination(self):
        v = lost_voice(places=[EmergencyTests().place()])
        v.try_handle("engage emergency protocol")
        self.assertIn("PoiPlotting", v.narrator.said)
        self.assertNotIn("RouteNoDestination", v.narrator.said)

    def test_separate_command_never_plots_a_neutron_route(self):
        v = EmergencyTests().make(places=[EmergencyTests().place()])       # a destination IS set here
        v.try_handle("take me to the nearest point of interest")
        self.assertEqual(v.narrator.said, ["PoiPlotting"])
        self.assertIsNone(v._emergency)
        self.assertEqual(v.spansh.routes, [])

    def test_clipboard_when_the_plotter_is_off_and_edge_cases(self):
        v = lost_voice(places=[EmergencyTests().place()], auto_plot=False)
        v.try_handle("plot me a route to the nearest poi")
        self.assertEqual(v.narrator.said, ["PoiManual"])
        self.assertEqual(v.follower.copied, ["Landmark"])
        v = lost_voice(places=[])
        v.try_handle("i am lost")
        self.assertEqual(v.narrator.said, ["EmergencyNone"])
        v = lost_voice(position=None)
        v.try_handle("nearest landmark")
        self.assertEqual(v.narrator.said, ["EmergencyNoPosition"])

    def test_with_a_destination_the_old_protocol_still_runs(self):
        v = EmergencyTests().make(places=[EmergencyTests().place()])
        v.try_handle("emergency protocol")
        self.assertIn("EmergencyPlotting", v.narrator.said)
        self.assertEqual(v._emergency["destination"], "Colonia")

    def test_lines_exist(self):
        data = json.load(open("voicepacks/default/route.json", encoding="utf-8"))
        for key in ("PoiPlotting", "PoiManual"):
            self.assertTrue(data[key])


class NomadRace(unittest.TestCase):
    """Status.json lags the journal: it still says 'main ship' for a moment after LaunchVessel."""
    SHIP, NOMAD = 153157640, 203423816

    def test_nomad_survives_a_stale_main_ship_reading(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": self.SHIP}, initial=True)
        processor.handle_line('{"event":"LaunchVessel","VesselType":"whatever"}', silent=True)
        reader.handle_status({"Flags": self.SHIP})                 # the old reading, one more time
        self.assertTrue(processor.state.in_nomad)
        reader.handle_status({"Flags": self.NOMAD})
        self.assertEqual(reader._vehicle, "Nomad")
        reader.handle_status({"Flags": self.SHIP})                 # comes home
        self.assertFalse(processor.state.in_nomad)
        self.assertIn("NomadDocked", [e.name for e in heard])      # so the hardpoints get put away


class SetupPageAndUpdater(unittest.TestCase):
    def test_listening_is_a_section_of_voice(self):
        from ui.settings_model import SECTION_OF
        self.assertEqual(SECTION_OF["listening"], "voice")

    def test_stage_update_copes_with_a_leftover_folder(self):
        import hashlib
        import io
        import zipfile
        import importlib.util
        # load the real file by path: another test (test_launcher) swaps a stub in for core.updater
        spec = importlib.util.spec_from_file_location("real_updater_for_test", Path(__file__).resolve().parent.parent / "core" / "updater.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        folder = Path(tempfile.mkdtemp())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("main.py", "print(1)")
            z.writestr("core/x.py", "")
        data = buf.getvalue()
        sha = hashlib.sha256(data).hexdigest()

        class Reply:
            def __init__(self, body): self.body = body
            def read(self, n=-1): b, self.body = self.body, b""; return b
            def __enter__(self): return self
            def __exit__(self, *a): return False
            headers = {}
        def opener(request, timeout=None):
            url = getattr(request, "full_url", request)
            return Reply(sha.encode() if "sha" in url else data)
        (folder / "pending").mkdir()
        from unittest import mock
        with mock.patch("shutil.rmtree", lambda *a, **k: None):        # Windows could not delete it
            result = updater.stage_update({"version": "9.9.9", "zip_url": "http://z/zip", "sha_url": "http://z/sha"}, folder, opener=opener)
        self.assertTrue((result / "main.py").is_file())


class OverlayPeek(unittest.TestCase):
    def test_new_route_shows_over_a_game_screen(self):
        from journal.game_state import GameState
        from ui import route_overlay as ro
        from tests.test_route_map import Settings, follower_with
        from navigation import galaxy_map as gm
        state = GameState()
        state.gui_focus = 6
        f = follower_with(gm.test_route())
        self.assertIsNone(ro.wanted_mode(Settings(), state, f))
        self.assertEqual(ro.wanted_mode(Settings(), state, f, fresh=True), "route")
        state.route_map_hidden = True
        self.assertIsNone(ro.wanted_mode(Settings(), state, f, fresh=True))

    def test_backfill_asks_for_the_destination_first(self):
        from ui import route_overlay as ro
        from tests.test_route_map import follower_with
        f = follower_with([{"system": n, "neutron": False, "jumps": 1} for n in "ABC"])
        asked = []
        ro.backfill_positions(f, lambda n: asked.append(n) or (1.0, 2.0, 3.0), sleep=lambda s: None)
        self.assertEqual(asked[0], "C")

    def test_view_is_wider_now(self):
        from navigation import galaxy_map as gm
        view = gm.fit_view([(0, 0), (1000, 1000)])
        self.assertGreaterEqual(view.span, 1000 * 1.8)


class Repeats(unittest.TestCase):
    def test_small_pools_use_every_line_first(self):
        from personality.dialogue import DialogueManager as Dialogue
        import random
        d = Dialogue.__new__(Dialogue)
        d._recent = {}
        d.rng = random.Random(3)
        from collections import namedtuple
        L = namedtuple("L", "text")
        lines = [L("a%d" % i) for i in range(7)]
        d.pool = lambda *a, **k: lines
        seen = [d.pick("k").text for _ in range(7)]
        self.assertEqual(len(set(seen)), 7)


class VoiceWords(unittest.TestCase):
    def test_closed_bio_overlay(self):
        from control.bio_voice import BioOverlayVoice
        from journal.game_state import GameState
        state = GameState()
        v = BioOverlayVoice(lambda: state)
        self.assertTrue(v.try_handle("closed bio overlay"))
        self.assertTrue(state.bio.hidden)


if __name__ == "__main__":
    unittest.main()
