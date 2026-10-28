"""0.77.1: fixes from the 28 Oct evening log (Nomad pips and hardpoints, mining chatter, overlay, install folder, push-to-talk page)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from journal.bio_predict import BioBody, BioPredictor
from tests.test_status_reader import make_processor
from journal.status_reader import StatusReader

HARDPOINTS, CARGO_SCOOP, IN_DANGER, MAIN_SHIP = 1 << 6, 1 << 9, 1 << 22, 1 << 24


class PagesTests(unittest.TestCase):
    def test_push_to_talk_is_on_the_listening_page_under_voice(self):
        from ui import settings_model as m
        source = Path(m.__file__).read_text(encoding="utf-8")
        listening = source[source.index('Page("listening"'):source.index('Page("controls"')]
        for key in ("ptt.mode", "ptt.button", "ptt.beep", "ptt.skip_wake"):
            self.assertIn(key, listening)
        controls = source[source.index('Page("controls"'):source.index('Page("chat"')]
        self.assertNotIn('"ptt.mode"', controls)


class MiningQuietTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})
        self.reader.handle_status({"Flags": MAIN_SHIP}, initial=True)

    def names(self):
        return [e.name for e in self.heard]

    def test_cargo_scoop_is_spoken_when_not_mining(self):
        self.reader.handle_status({"Flags": MAIN_SHIP | CARGO_SCOOP})
        self.assertIn("CargoScoopDeployed", self.names())

    def test_cargo_scoop_is_quiet_while_mining(self):
        self.processor.handle_line('{"event":"LaunchDrone","Type":"collection"}', silent=True)
        self.reader.handle_status({"Flags": MAIN_SHIP | CARGO_SCOOP})
        self.reader.handle_status({"Flags": MAIN_SHIP})
        self.assertNotIn("CargoScoopDeployed", self.names())
        self.assertNotIn("CargoScoopRetracted", self.names())

    def test_danger_is_quiet_while_mining_but_not_after_an_attack(self):
        self.processor.handle_line('{"event":"LaunchDrone","Type":"prospector"}', silent=True)
        self.reader.handle_status({"Flags": MAIN_SHIP | IN_DANGER})
        self.assertNotIn("InDanger", self.names())
        self.reader.handle_status({"Flags": MAIN_SHIP})
        self.processor.handle_line('{"event":"UnderAttack","Target":"You"}', silent=True)
        self.reader.handle_status({"Flags": MAIN_SHIP | IN_DANGER})
        self.assertIn("InDanger", self.names())


class NomadPipsTests(unittest.TestCase):
    def test_no_auto_pips_in_the_nomad(self):
        from control.combat_assist import CombatAssist
        state = SimpleNamespace(status_flags=HARDPOINTS | (1 << 26), in_nomad=True)
        assist = CombatAssist(None, SimpleNamespace(get=lambda k, d=None: d), None, None, None, lambda: state)
        self.assertFalse(assist.fighting())
        state.in_nomad = False
        state.status_flags = HARDPOINTS | MAIN_SHIP
        self.assertTrue(assist.fighting())


class OverlayTests(unittest.TestCase):
    def mapped(self):
        bio = BioPredictor.__new__(BioPredictor)
        bio.reset()
        body = BioBody("Sys B 2", "B 2", 4)
        body.genera = ["Osseus"]
        body.body_id = 12
        bio.bodies = {"Sys B 2": body}
        return bio

    def test_overlay_hides_when_the_jump_starts(self):
        bio = self.mapped()
        self.assertFalse(bio.is_leaving())
        bio.start_leaving()
        self.assertTrue(bio.is_leaving())
        bio.reset()
        self.assertFalse(bio.is_leaving())

    def test_going_back_to_a_mapped_planet_brings_its_view_back(self):
        bio = self.mapped()
        bio.note_target(5)                      # something else targeted: nothing to show
        self.assertEqual(bio.focus, "")
        bio.note_target(12)                     # the mapped planet targeted again
        self.assertEqual(bio.focus, "Sys B 2")
        bio.note_target(5)                      # target something else: the list returns
        self.assertEqual(bio.focus, "")

    def test_landing_near_it_brings_the_view_back(self):
        bio = self.mapped()
        bio.note_target(None, near="Sys B 2", hold=True)
        self.assertEqual(bio.focus, "Sys B 2")


class InstallFolderTests(unittest.TestCase):
    def test_remembered_install_folder(self):
        import os
        from launcher import launcher as L
        with tempfile.TemporaryDirectory() as tmp:
            old = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "STARLING_HOME")}
            os.environ["LOCALAPPDATA"] = tmp
            os.environ.pop("STARLING_HOME", None)
            try:
                self.assertTrue(L.needs_choice())
                L.save_home(Path(tmp) / "Games" / "Starling")
                self.assertFalse(L.needs_choice())
                self.assertEqual(L.install_home(), Path(tmp) / "Games" / "Starling")
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_existing_install_is_never_asked(self):
        import os
        from launcher import launcher as L
        with tempfile.TemporaryDirectory() as tmp:
            old = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "STARLING_HOME")}
            os.environ["LOCALAPPDATA"] = tmp
            os.environ.pop("STARLING_HOME", None)
            try:
                (Path(tmp) / "Starling" / "app").mkdir(parents=True)
                (Path(tmp) / "Starling" / "app" / "main.py").write_text("x")
                self.assertFalse(L.needs_choice())
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
