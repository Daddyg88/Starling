"""Guardian blueprint sites: the commands, the 1000 light year rule, the two-stop vessel route, and the spoken guides."""

import json
import tempfile
import unittest
from pathlib import Path

from navigation import guardian
from tests import test_neutron


class Spansh(test_neutron.FakeSpansh):
    def __init__(self, coords=None):
        super().__init__()
        self.coords = coords or {}

    def coordinates(self, name):
        return self.coords.get(name)


class Parse(unittest.TestCase):
    def test_phrases(self):
        cases = [("plot me a route to guardian weapon blueprint", ("weapon", "go")),
                 ("take me to the guardian module blueprints", ("module", "go")),
                 ("plot a route to the guardian vessel blueprint", ("vessel", "go")),
                 ("route to guardian fighter blue print", ("vessel", "go")),
                 ("how do i get the guardian weapon blueprints", ("weapon", "guide")),
                 ("how to get the guardian module blue prints", ("module", "guide")),
                 ("where is the guardian vessel blueprint", ("vessel", "where"))]
        for text, expected in cases:
            self.assertEqual(guardian.parse(text), expected, text)
        self.assertIsNone(guardian.parse("plot a route to colonia"))
        self.assertIsNone(guardian.parse("how do i get the guardian"))

    def test_key(self):
        self.assertTrue(guardian.is_key("ancientkey"))
        self.assertTrue(guardian.is_key("Ancient Key"))
        self.assertFalse(guardian.is_key("ancientrelic"))


class Go(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setup_voice(self, system="Sol", pos=(0, 0, 0), coords=None):
        v = self.build(system=system, spansh=Spansh(coords))
        self.state.star_pos = pos
        self.macro = []
        v.plot_macro = lambda s: self.macro.append(s) or (True, "")
        v.sleep = lambda s: None
        v.journal_folder_provider = lambda: None
        return v

    def test_close_site_uses_the_galaxy_map_far_site_a_neutron_route(self):
        v = self.setup_voice(coords={"Synuefe EU-Q C21-10": (-300.0, 0.0, 400.0)})
        v.try_handle("plot me a route to guardian weapon blueprint")
        self.assertEqual(self.macro, ["Synuefe EU-Q C21-10"])
        self.assertEqual(self.keys(), ["GuardianNear"])
        v = self.setup_voice(coords={"Synuefe EU-Q C21-10": (-3000.0, 0.0, 4000.0)})
        v.try_handle("plot me a route to guardian weapon blueprint")
        self.assertEqual(self.macro, [])
        self.assertEqual(self.keys()[0], "GuardianFar")
        self.assertIn("route", [c[0] for c in self.spansh.asked])

    def test_unknown_distance_is_a_neutron_route(self):
        v = self.setup_voice()
        v.try_handle("take me to the guardian module blueprints")
        self.assertEqual(self.keys()[0], "GuardianFarUnknown")
        self.assertIn(("find", "Synuefe NL-N C23-4"), self.spansh.asked)

    def test_vessel_goes_to_the_beacon_then_the_structure_when_the_key_is_aboard(self):
        near = {"Synuefe KU-F B44-4": (0.0, 0.0, 700.0), "Synuefe EU-Q C21-15": (0.0, 0.0, 740.0)}
        v = self.setup_voice(coords=near)
        v.try_handle("plot me a route to guardian vessel blueprint")
        self.assertEqual(self.macro, ["Synuefe KU-F B44-4"])
        self.assertEqual(v.vessel_stage, 1)
        from core.event_bus import Event
        v.on_cargo(Event("CollectCargo", {"Type": "ancientrelic"}))
        self.assertEqual(self.macro, ["Synuefe KU-F B44-4"])             # a relic is not the key
        v.on_cargo(Event("CollectCargo", {"Type": "ancientkey"}))
        self.assertEqual(self.macro, ["Synuefe KU-F B44-4", "Synuefe EU-Q C21-15"])
        self.assertIn("GuardianKeyAboard", self.keys())
        self.assertEqual(v.vessel_stage, 2)

    def test_asking_again_with_the_key_goes_to_the_structure(self):
        v = self.setup_voice(coords={"Synuefe EU-Q C21-15": (0.0, 0.0, 700.0)})
        v.vessel_stage = 2
        v.try_handle("take me to the guardian fighter blueprint")
        self.assertEqual(self.macro, ["Synuefe EU-Q C21-15"])

    def test_alternative_site(self):
        v = self.setup_voice()
        v.try_handle("plot a route to the alternative guardian weapon blueprint")
        self.assertIn(("find", "Synuefe GV-T b50-4"), self.spansh.asked)

    def test_setting_off_only_tells_does_not_plot(self):
        v = self.setup_voice(coords={"Synuefe EU-Q C21-15": (0.0, 0.0, 700.0)})
        v.settings.set("guardian.auto_plot_key", False)
        v.vessel_stage = 1
        from core.event_bus import Event
        v.on_cargo(Event("CollectCargo", {"Type": "ancientkey"}))
        self.assertEqual(self.macro, [])
        self.assertIn("GuardianKeyAboard", self.keys())

    def test_the_guide_is_said_in_order(self):
        v = self.setup_voice()
        v.narr = None
        said = []
        v.narrator.say = lambda key, fields=None: (said.append(key) or key in self.lines)
        self.lines = {"GuardianGuide_Weapon_%d" % n for n in range(1, 9)}
        v.try_handle("how do i get the guardian weapon blueprints")
        self.assertEqual(said[:3], ["GuardianGuide_Weapon_1", "GuardianGuide_Weapon_2", "GuardianGuide_Weapon_3"])


class Data(unittest.TestCase):
    def test_every_step_has_lines(self):
        pack = json.loads(Path("voicepacks/default/guardian.json").read_text(encoding="utf-8"))
        for kind, count in (("Module", 7), ("Weapon", 8), ("Vessel", 8)):
            for n in range(1, count + 1):
                self.assertIn("GuardianGuide_%s_%d" % (kind, n), pack)
        for key in ("GuardianNear", "GuardianFar", "GuardianFarUnknown", "GuardianHere", "GuardianPlotOff", "GuardianWhere", "GuardianKeyAboard"):
            self.assertIn(key, pack)

    def test_sites_file(self):
        sites = guardian.load()
        self.assertEqual(sites["vessel"]["steps"][0]["system"], "Synuefe KU-F B44-4")
        self.assertEqual(len(sites["vessel"]["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
