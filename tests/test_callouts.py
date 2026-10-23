import json
import random
import unittest
from pathlib import Path

from core import paths
from events import fsd_jump
from navigation.voice import RouteVoice, is_caspian
from personality import line_keys
from personality.dialogue import DialogueManager
from journal.status_reader import StatusReader
from tests.helpers import make_processor
from tests.test_flavour import make


def jump(system="Sol"):
    return json.dumps({"event": "FSDJump", "StarSystem": system, "JumpDist": 8.0, "FuelUsed": 1.0, "FuelLevel": 20.0})


def scan(name="Sol A 1", discovered=True, gravity=4.9, kelvin=288.0):
    return json.dumps({"event": "Scan", "BodyName": name, "WasDiscovered": discovered, "SurfaceGravity": gravity,
                       "SurfaceTemperature": kelvin, "ScanType": "AutoScan"})


class GlideTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})
        self.glide = 1 << 12

    def start_glide(self):
        self.reader.handle_status({"Flags": 0, "Flags2": 0})
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": 0})
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": self.glide})

    def test_scan_remembers_gravity_in_g_and_temperature(self):
        self.processor.handle_line(scan("Planet 1", gravity=19.6133, kelvin=402.4))
        facts = self.processor.state.bodies["Planet 1"]
        self.assertAlmostEqual(facts["gravity"], 2.0, places=2)
        self.assertEqual(round(facts["temperature"]), 402)

    def test_glide_names_temperature_and_gravity_of_the_planet(self):
        self.processor.handle_line(scan("Planet 1", gravity=4.9, kelvin=288.0))
        self.processor.state.current_body = "Planet 1"
        self.start_glide()
        glides = [e for e in self.heard if e.name == "GlideStarted"]
        self.assertEqual(len(glides), 1)
        self.assertEqual(glides[0].data["temperature"], 288)
        self.assertEqual(glides[0].data["gravity"], "0.50")
        self.assertFalse(glides[0].data["heavy"])

    def test_glide_without_a_scan_still_says_glide(self):
        self.start_glide()
        glide = [e for e in self.heard if e.name == "GlideStarted"][0]
        self.assertNotIn("temperature", glide.data)
        self.assertEqual(line_keys.keys_for(glide), ["GlideStarted"])

    def test_heavy_world_uses_the_heavy_lines_first(self):
        self.processor.handle_line(scan("Big", gravity=29.4, kelvin=300))
        self.processor.state.current_body = "Big"
        self.start_glide()
        glide = [e for e in self.heard if e.name == "GlideStarted"][0]
        self.assertEqual(line_keys.keys_for(glide)[0], "GlideStarted_Heavy")

    def test_status_json_body_name_sets_the_current_body(self):
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": 0, "BodyName": "Sol A 3"})
        self.assertEqual(self.processor.state.current_body, "Sol A 3")


class JumpCallouts(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()

    def names(self):
        return [e.name for e in self.heard]

    def test_scoopable_flag_for_each_star_class(self):
        start = self.processor.registry["StartJump"]
        for star, expected in (("G", True), ("M", True), ("O", True), ("N", False), ("H", False), ("L", False), ("D", False), ("T", False)):
            data = start.handle({"event": "StartJump", "JumpType": "Hyperspace", "StarClass": star})
            self.assertEqual(data["Scoopable"], expected, star)

    def test_scoop_keys(self):
        class E:
            name = "StartJump"
            def __init__(self, data): self.data = data
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace", "Scoopable": True})), ["StartJump_Scoop", "StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace", "Scoopable": False})), ["StartJump_NoScoop", "StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace"})), ["StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Supercruise", "Scoopable": True})), [])

    def test_first_scan_in_an_undiscovered_system_is_announced_once(self):
        self.processor.handle_line(jump("Nowhere"))
        self.processor.handle_line(scan("Nowhere A", discovered=False))
        self.processor.handle_line(scan("Nowhere B", discovered=False))
        found = [e for e in self.heard if e.name == "UndiscoveredSystem"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].data["StarSystem"], "Nowhere")

    def test_discovered_system_is_quiet(self):
        self.processor.handle_line(jump("Sol"))
        self.processor.handle_line(scan("Sol A", discovered=True))
        self.assertNotIn("UndiscoveredSystem", self.names())

    def test_replaying_old_journal_lines_is_silent(self):
        self.processor.handle_line(jump("Nowhere"), silent=True)
        self.processor.handle_line(scan("Nowhere A", discovered=False), silent=True)
        self.assertNotIn("UndiscoveredSystem", self.names())
        self.processor.handle_line(scan("Nowhere B", discovered=False))     # the flag was used up by the silent replay
        self.assertNotIn("UndiscoveredSystem", self.names())

    def test_jumps_left_said_when_the_dice_allow(self):
        old = fsd_jump.random.random
        fsd_jump.random.random = lambda: 0.0
        try:
            self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 5})
            self.processor.handle_line(jump())
        finally:
            fsd_jump.random.random = old
        left = [e for e in self.heard if e.name == "JumpsLeft"]
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0].data["jumps"], 5)
        self.assertEqual(line_keys.keys_for(left[0]), ["JumpsLeft"])

    def test_jumps_left_stays_quiet_when_the_dice_say_no(self):
        old = fsd_jump.random.random
        fsd_jump.random.random = lambda: 0.99
        try:
            self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 5})
            self.processor.handle_line(jump())
        finally:
            fsd_jump.random.random = old
        self.assertNotIn("JumpsLeft", self.names())

    def test_last_jump_is_always_mentioned_and_not_repeated(self):
        self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 1})
        self.processor.handle_line(jump())
        self.processor.handle_line(jump("Elsewhere"))      # no new target: nothing more to say
        left = [e for e in self.heard if e.name == "JumpsLeft"]
        self.assertEqual(len(left), 1)
        self.assertEqual(line_keys.keys_for(left[0]), ["JumpsLeft_Last"])

    def test_no_route_no_callout(self):
        self.processor.handle_line(jump())
        self.assertNotIn("JumpsLeft", self.names())


class NomadTests(unittest.TestCase):
    def test_recovering_the_nomad_is_announced(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        srv = 1 << 26
        reader.handle_status({"Flags": 0})
        reader.handle_status({"Flags": 1 << 24})
        processor.state.in_nomad = True
        reader.handle_status({"Flags": srv})
        reader.handle_status({"Flags": 1 << 24})
        self.assertIn("NomadDocked", [e.name for e in heard])

    def test_recovering_a_normal_srv_is_not_the_nomad(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 0})
        reader.handle_status({"Flags": 1 << 24})
        reader.handle_status({"Flags": 1 << 26})
        reader.handle_status({"Flags": 1 << 24})
        self.assertNotIn("NomadDocked", [e.name for e in heard])


class CaspianTests(unittest.TestCase):
    class State:
        def __init__(self, ship=None, model=None):
            self.ship, self.ship_model = ship, model

    class Settings:
        def __init__(self, **values): self.values = values
        def get(self, key, default=None): return self.values.get(key, default)

    def voice(self, state, **values):
        values.setdefault("neutron.supercharge", 4)
        return RouteVoice(None, None, None, self.Settings(**values), lambda: state)

    def test_caspian_is_recognised_by_either_name(self):
        self.assertTrue(is_caspian(self.State("explorer_nx")))
        self.assertTrue(is_caspian(self.State("Caspian Explorer")))
        self.assertTrue(is_caspian(self.State(None, "Caspian Explorer")))
        self.assertFalse(is_caspian(self.State("anaconda", "Anaconda")))
        self.assertFalse(is_caspian(None))

    def test_x6_in_the_caspian_and_the_setting_elsewhere(self):
        self.assertEqual(self.voice(self.State("explorer_nx")).supercharge(), 6)
        self.assertEqual(self.voice(self.State("anaconda")).supercharge(), 4)
        self.assertEqual(self.voice(self.State("anaconda"), **{"neutron.supercharge": 6}).supercharge(), 6)

    def test_auto_x6_can_be_switched_off(self):
        self.assertEqual(self.voice(self.State("explorer_nx"), **{"neutron.auto_x6": False}).supercharge(), 4)


class PetNameTests(unittest.TestCase):
    def test_own_names_are_read_from_the_box(self):
        f, _d = make()
        f.settings.set("personality.custom_pet_names", "Captain Fluffy,  Sparky ;Boss\nNo. 1,, ")
        self.assertEqual(f.custom_names(), ["Captain Fluffy", "Sparky", "Boss", "No. 1"])

    def test_own_names_are_used(self):
        f, _d = make(roll=0.0)
        f.settings.set("personality.custom_pet_names", "Captain Fluffy")
        self.assertEqual(f.rename("Docked, Commander.", always=True), "Docked, Captain Fluffy.")

    def test_empty_box_changes_nothing(self):
        f, _d = make(roll=0.0)
        f.settings.set("personality.custom_pet_names", "")
        self.assertEqual(f.custom_names(), [])
        self.assertNotIn("Captain Fluffy", f.rename("Docked, Commander.", always=True))

    def test_rarely_used_when_she_is_upset(self):
        f, _d = make(mood="Upset", roll=0.5)
        f.settings.set("personality.custom_pet_names", "Captain Fluffy")
        self.assertNotIn("Captain Fluffy", f.rename("Docked, Commander.", always=True))


class DialogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()

    def test_every_new_key_has_lines(self):
        for key in ("GlideStarted_Info", "GlideStarted_Heavy", "StartJump_Scoop", "StartJump_NoScoop", "UndiscoveredSystem",
                    "JumpsLeft", "JumpsLeft_Last", "NomadDocked"):
            self.assertTrue(self.d.lines.get(key), key)

    def test_undiscovered_system_has_lots_of_lines(self):
        self.assertGreaterEqual(len(self.d.lines["UndiscoveredSystem"]), 50)

    def test_placeholders_are_known(self):
        allowed = {"GlideStarted": {"temperature", "gravity"}, "StartJump": {"StarSystem"}, "UndiscoveredSystem": {"StarSystem"},
                   "JumpsLeft": {"jumps"}, "NomadDocked": set()}
        import string
        for key, lines in self.d.lines.items():
            base = key.split("_")[0]
            if key.startswith(("GlideStarted_", "StartJump_", "UndiscoveredSystem", "JumpsLeft", "NomadDocked")):
                for line in lines:
                    names = {f for _t, f, _s, _c in string.Formatter().parse(line.text) if f}
                    self.assertLessEqual(names, allowed[base], (key, line.text))

    def test_no_duplicate_lines_in_a_key(self):
        for key in ("UndiscoveredSystem", "StartJump_Scoop", "StartJump_NoScoop", "JumpsLeft", "GlideStarted_Info"):
            texts = [l.text for l in self.d.lines[key]]
            self.assertEqual(len(texts), len(set(texts)), key)


if __name__ == "__main__":
    unittest.main()
