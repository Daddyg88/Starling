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
        self.reader.danger_hold = 0
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


class NyxLogTests(unittest.TestCase):
    def test_fire_key_is_ignored_while_a_panel_is_open(self):
        from control.combat_assist import CombatAssist
        state = SimpleNamespace(status_flags=HARDPOINTS | MAIN_SHIP, in_nomad=False, gui_focus=2)
        assist = CombatAssist(None, SimpleNamespace(get=lambda k, d=None: d), None, None, None, lambda: state)
        self.assertFalse(assist.fighting())
        state.gui_focus = 0
        self.assertTrue(assist.fighting())

    def test_engage_fsd_is_the_jump_not_the_scanner(self):
        from control.matcher import Matcher
        m = Matcher()
        for text in ("Engage FSD.", "Engage frame shift drive.", "charge the fsd"):
            self.assertEqual(m.match(text).command.id, "hyperspace", text)
        self.assertEqual(m.match("engage fss").command.id, "fss_enter")

    def test_danger_must_stay_on_and_is_quiet_just_after_a_jump(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        now = [100.0]
        reader._clock = lambda: now[0]
        reader.handle_status({"Flags": MAIN_SHIP}, initial=True)
        reader.handle_status({"Flags": MAIN_SHIP | IN_DANGER})
        reader.handle_status({"Flags": MAIN_SHIP})                       # flickered off at once: nothing said
        self.assertNotIn("InDanger", [e.name for e in heard])
        reader.handle_status({"Flags": MAIN_SHIP | IN_DANGER})
        now[0] += 4
        reader.handle_status({"Flags": MAIN_SHIP | IN_DANGER})           # stayed on 4 s
        self.assertIn("InDanger", [e.name for e in heard])

    def test_no_danger_call_right_after_entering_supercruise(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        now = [100.0]
        reader._clock = lambda: now[0]
        reader.handle_status({"Flags": MAIN_SHIP}, initial=True)
        reader.handle_status({"Flags": MAIN_SHIP | (1 << 4)})            # supercruise
        reader.handle_status({"Flags": MAIN_SHIP | (1 << 4) | IN_DANGER})
        now[0] += 4
        reader.handle_status({"Flags": MAIN_SHIP | (1 << 4) | IN_DANGER})
        self.assertNotIn("InDanger", [e.name for e in heard])


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


class DockJokeTests(unittest.TestCase):
    """0.77.4: funny lines when she is back aboard from the Nomad or the SRV."""

    @classmethod
    def setUpClass(cls):
        from core import paths
        from personality.dialogue import DialogueManager
        cls.d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()

    def test_lots_of_lines_for_both_events(self):
        for key in ("NomadDocked", "DockSRV"):
            self.assertGreaterEqual(len(self.d.lines[key]), 40, key)
            for mood in ("Sarcastic", "Close", "Frustrated"):
                self.assertGreaterEqual(len(self.d.lines["%s_%s" % (key, mood)]), 5, (key, mood))

    def test_no_duplicates_and_no_placeholders(self):
        import string
        for key, lines in self.d.lines.items():
            if not key.startswith(("NomadDocked", "DockSRV")):
                continue
            texts = [l.text for l in lines]
            self.assertEqual(len(texts), len(set(texts)), key)
            for text in texts:
                self.assertFalse([f for _t, f, _s, _c in string.Formatter().parse(text) if f], text)
                self.assertFalse(any(w in text.lower() for w in ("password", "pin number")), text)

    def test_every_mood_can_pick_a_line(self):
        for key in ("NomadDocked", "DockSRV"):
            for mood in ("Neutral", "Friendly", "Close", "Infatuated", "Sarcastic", "Frustrated", "Upset"):
                self.assertIsNotNone(self.d.pick(key, mood), (key, mood))

    def test_srv_has_a_speech_gap_so_she_does_not_nag(self):
        import json
        from core import paths
        data = json.loads((paths.CONFIG_DIR / "speech.json").read_text(encoding="utf-8"))
        self.assertIn("DockSRV", data["cooldown_seconds"])


class Log29OctTests(unittest.TestCase):
    """0.77.6: fixes from the 29 Oct evening log (lower-case memory lines, 'Lft', 'route 2', FSS log spam, '1 neutron stops')."""

    class Settings:
        def __init__(self, **v): self.v = v
        def get(self, k, d=None): return self.v.get(k, d)

    class Narrator:
        def __init__(self): self.said = []
        def say(self, key, fields=None): self.said.append((key, fields))

    class Follower:
        active = False

    def voice(self):
        from navigation.voice import RouteVoice
        narrator = self.Narrator()
        v = RouteVoice(self.Follower(), None, narrator, self.Settings(), lambda: None, spawn=lambda f: None)
        v.game_target = lambda: ""
        return v, narrator

    def test_catalogue_names_keep_their_capitals(self):
        for said, expected in (("plot a neutron route to lft 509", "LFT 509"), ("plot neutron route to hip 50045", "HIP 50045"),
                               ("plot neutron route to col 285 sector nx j c9 21", "Col 285 Sector Nx J C9 21")):
            self.assertEqual(self.voice()[0].try_handle(said), "Plotting a neutron route to " + expected)

    def test_microphone_two_means_to(self):
        self.assertEqual(self.voice()[0].try_handle("plot route 2 LFT 509"), "Plotting a neutron route to LFT 509")
        self.assertEqual(self.voice()[0].try_handle("plot neutron route too sol"), "Plotting a neutron route to Sol")

    def test_a_bare_catalogue_name_asks_for_the_number(self):
        v, narrator = self.voice()
        answer = v.try_handle("plot route to LFT")
        self.assertIn("Which LFT", answer)
        self.assertEqual(narrator.said[-1][0], "RouteNeedNumber")

    def test_singular_neutron_stop_and_jump(self):
        from navigation.voice import Narrator
        spoken = []
        speech = SimpleNamespace(say=lambda text, **k: spoken.append(text) or True)

        class Dialogue:
            def pick(self, key, mood, allow, prefer):
                return SimpleNamespace(text="Done. {stops} neutron stops, {left} jumps to {destination}.")
        settings = self.Settings(**{"personality.style": "info"})
        Narrator(lambda: speech, Dialogue(), settings).say("RouteReady", {"stops": 1, "left": 1, "destination": "LFT 898"})
        self.assertEqual(spoken[-1], "Done. 1 neutron stop, 1 jump to LFT 898.")

    def test_memory_lines_start_with_a_capital(self):
        from memory.recall import MemoryRecall
        import inspect
        source = inspect.getsource(MemoryRecall._say)
        self.assertIn(".upper()", source)

    def test_same_fss_signal_is_logged_once_per_system(self):
        from events.fss_signal_discovered import FSSSignalDiscovered
        state = SimpleNamespace(system="Sol")
        entry = {"event": "FSSSignalDiscovered", "SignalName": "$USS_DegradedEmissions;", "USSType": "$USS_Type_Salvage;", "SystemAddress": 1}
        event = FSSSignalDiscovered()
        with self.assertLogs("starling.fss_signal", level="INFO") as logs:
            for _ in range(5):
                event.update_state(entry, state)
        self.assertEqual(len(logs.output), 1)
