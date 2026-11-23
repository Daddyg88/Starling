import gzip
import json
import os
import tempfile
import unittest

from navigation.neutron_router import NeutronRouter, load_list, jumps_for, LocalRouteError
from tools import build_neutron_list as build


def line(name, x, y, z, neutron):
    bodies = [{"subType": "Neutron Star" if neutron else "K (Yellow-Orange) Star"}]
    return (json.dumps({"name": name, "id64": 1, "coords": {"x": x, "y": y, "z": z}, "bodies": bodies}) + ",\n").encode()


class Tool(unittest.TestCase):
    def test_only_neutron_systems_kept(self):
        lines = [b"[\n", line("A", 0, 0, 0, False), line("B", 1, 2, 3, True), b"]\n"]
        self.assertEqual([r[0] for r in build.neutron_systems(lines)], ["B"])

    def test_build_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "g.json.gz"), os.path.join(d, "n.csv.gz")
            with gzip.open(src, "wb") as f:
                f.write(b"[\n" + line("N1", 100, 0, 0, True) + line("X", 5, 5, 5, False) + b"]\n")
            self.assertEqual(build.build(src, out), 1)
            self.assertEqual(load_list(out), [("N1", (100.0, 0.0, 0.0))])

    def test_missing_file_is_empty(self):
        self.assertEqual(load_list("/nonexistent/x.gz"), [])


class Route(unittest.TestCase):
    def test_jumps(self):
        self.assertEqual(jumps_for(50, 50), 1)
        self.assertEqual(jumps_for(200, 50, 200), 1)
        self.assertEqual(jumps_for(300, 50, 200), 3)

    def test_chain_of_neutrons_beats_walking(self):
        stars = [("N%d" % i, (150.0 * i, 0.0, 0.0)) for i in range(1, 7)]
        r = NeutronRouter(stars)
        wps = r.route("Home", (0, 0, 0), "Far", (1000, 0, 0), 50, 4)
        self.assertEqual(wps[0]["system"], "Home")
        self.assertEqual(wps[-1]["system"], "Far")
        self.assertTrue(any(w["neutron"] for w in wps))
        self.assertLess(sum(w["jumps"] for w in wps), 20)       # walking would be 20 jumps
        self.assertTrue(all(set(w) >= {"system", "neutron", "jumps", "distance_left"} for w in wps))

    def test_no_list_raises(self):
        with self.assertRaises(LocalRouteError):
            NeutronRouter([]).route("a", (0, 0, 0), "b", (10, 0, 0), 50)

    def test_no_stars_goes_direct(self):
        wps = NeutronRouter([("Z", (0, 5000, 0))]).route("a", (0, 0, 0), "b", (100, 0, 0), 50)
        self.assertEqual([w["system"] for w in wps], ["a", "b"])
        self.assertEqual(wps[-1]["jumps"], 2)


if __name__ == "__main__":
    unittest.main()
