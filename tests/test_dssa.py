"""DSSA carriers: reading the list, finding the nearest (in a region), the 1500 light year rule."""

import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from navigation import dssa
from navigation.regions import find_region
from tests import test_neutron
from tests.test_guardian import Spansh

CSV_A = """Name,Callsign,Current System,Status,X,Y,Z
DSSA Aristarchos,ABC-123,Eocs Aihm XX-U d2-6,Deployed,22759.4,108.3,-11033.4
DSSA Ghost,DEF-456,Nowhere,Decommissioned,1,2,3
DSSA Near,GHI-789,Sol Neighbour,Deployed,10,0,10
"""
CSV_B = """carrier,system,destination system,coordinates
DSSA One,Alpha,Far Away,"100.5 / 20 / 300"
DSSA Two,Beta,Alpha,
"""


class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Parse(unittest.TestCase):
    def test_columns_found_by_name(self):
        rows = dssa.parse_csv(CSV_A)
        self.assertEqual([r["name"] for r in rows], ["DSSA Aristarchos", "DSSA Near"])      # the decommissioned one is skipped
        self.assertEqual(rows[0]["system"], "Eocs Aihm XX-U d2-6")
        self.assertEqual(rows[0]["pos"], [22759.4, 108.3, -11033.4])

    def test_other_layout_uses_current_not_destination(self):
        rows = dssa.parse_csv(CSV_B)
        self.assertEqual([(r["name"], r["system"], r["pos"]) for r in rows],
                         [("DSSA One", "Alpha", [100.5, 20.0, 300.0]), ("DSSA Two", "Beta", None)])

    def test_rubbish(self):
        self.assertEqual(dssa.parse_csv(""), [])
        self.assertEqual(dssa.parse_csv("only a header\n"), [])

    def test_phrases(self):
        cases = {"plot me a route to the nearest dssa in the norma expanse": "norma expanse",
                 "plot a route to the nearest dssa": "",
                 "take me to the closest d s s a carrier": "",
                 "go to a dissa carrier in the void": "void"}
        for text, tail in cases.items():
            self.assertEqual(dssa.parse_request(text), tail, text)
        for text in ("plot a route to colonia", "tell me about the weather", "what is a dssa"):
            self.assertIsNone(dssa.parse_request(text), text)
        self.assertEqual(dssa.find_region_named("norma expanse"), "Norma Expanse")
        self.assertEqual(dssa.find_region_named("odins hold"), "Odin's Hold")
        self.assertIsNone(dssa.find_region_named("sol"))


class Load(unittest.TestCase):
    def test_download_cache_and_offline_fallback(self):
        cache = Path(tempfile.mkdtemp()) / "c.json"
        calls = []

        def opener(request, timeout=0):
            calls.append(request.full_url)
            return FakeReply(CSV_A.encode())
        d = dssa.Dssa(cache, opener=opener)
        self.assertTrue(d.refresh())
        self.assertEqual(len(d.carriers), 2)
        self.assertTrue(d.refresh())                           # fresh: no second download
        self.assertEqual(len(calls), 1)

        def broken(request, timeout=0):
            raise OSError("offline")
        again = dssa.Dssa(cache, opener=broken, clock=lambda: time.time() + 99 * 3600)      # old copy, no internet
        self.assertTrue(again.refresh())
        self.assertEqual(len(again.carriers), 2)
        self.assertFalse(dssa.Dssa(None, opener=broken).refresh())

    def test_nearest_and_region(self):
        d = dssa.Dssa(None)
        d.carriers = [{"name": "Far", "system": "F", "pos": [22759.4, 108.3, -11033.4]},
                      {"name": "Near", "system": "N", "pos": [10.0, 0.0, 10.0]},
                      {"name": "NoPos", "system": "Unknown", "pos": None}]
        d.spansh = Spansh({"Unknown": (1.0, 1.0, 1.0)})
        best, miles = d.nearest((0.0, 0.0, 0.0))
        self.assertEqual(best["name"], "NoPos")                # coordinates were looked up through Spansh
        region = find_region(22759.4, 108.3, -11033.4)[1]
        best, _ = d.nearest((0.0, 0.0, 0.0), region)
        self.assertEqual(best["name"], "Far")
        self.assertIsNone(d.nearest((0.0, 0.0, 0.0), "The Void") if region != "The Void" else None)


class Voice(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setup_voice(self, miles, system="Sol"):
        v = self.build(system=system, spansh=Spansh({}))
        self.state.star_pos = (0.0, 0.0, 0.0)
        self.macro = []
        v.plot_macro = lambda s: self.macro.append(s) or (True, "")
        v.dssa.carriers = [{"name": "DSSA Test", "system": "Carrier Sys", "pos": [0.0, 0.0, miles]}]
        v.dssa.loaded_at = time.time()
        return v

    def test_inside_1500_uses_the_galaxy_map(self):
        v = self.setup_voice(1400)
        v.try_handle("plot me a route to the nearest dssa")
        self.assertEqual(self.macro, ["Carrier Sys"])
        self.assertEqual(self.keys()[-1], "DssaNear")

    def test_outside_1500_uses_a_neutron_route(self):
        v = self.setup_voice(1600)
        plotted = []
        v._plot_now = lambda name: plotted.append(name)
        v.try_handle("plot me a route to the nearest dssa")
        self.assertEqual(plotted, ["Carrier Sys"])
        self.assertEqual(self.macro, [])
        self.assertEqual(self.keys()[-1], "DssaFar")

    def test_unknown_region_and_no_carrier_there(self):
        v = self.setup_voice(100)
        self.assertIn("don't know a region", v.try_handle("plot a route to the nearest dssa in blorg"))
        self.assertEqual(self.keys()[-1], "DssaRegionUnknown")
        v.try_handle("plot a route to the nearest dssa in the void")
        self.assertEqual(self.keys()[-1], "DssaNone")

    def test_already_there(self):
        v = self.setup_voice(0, system="Carrier Sys")
        v.try_handle("plot a route to the nearest dssa")
        self.assertEqual(self.keys()[-1], "DssaHere")

    def test_setting_changes_the_limit(self):
        v = self.setup_voice(1600)
        self.settings.set("dssa.neutron_over_ly", 2000)
        v.try_handle("plot a route to the nearest dssa")
        self.assertEqual(self.macro, ["Carrier Sys"])


if __name__ == "__main__":
    unittest.main()
