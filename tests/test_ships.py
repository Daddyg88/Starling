import json
import unittest

from core import ships
from core.ships import ship_name
from tests.helpers import make_processor


class ShipNameTests(unittest.TestCase):
    def test_known_ships(self):
        for code, said in (("python", "Python"), ("cobramkiii", "Cobra Mark 3"), ("python_nx", "Python Mark 2"),
                           ("type9_military", "Type 10 Defender"), ("federation_corvette", "Federal Corvette"),
                           ("diamondbackxl", "Diamondback Explorer"), ("ferdelance", "Fer-de-Lance")):
            self.assertEqual(ship_name(code), said)

    def test_a_brand_new_ship_is_recognised_without_an_update(self):
        for code in ("anaconda_mkii", "Anaconda_MkII", "anacondamkii", "anaconda_mk2", "$anaconda_mkii_name;"):
            self.assertEqual(ship_name(code), "Anaconda Mark 2", code)
        self.assertEqual(ship_name("newship_mkiii"), "Newship Mark 3")
        self.assertEqual(ship_name("zorg"), "Zorg")

    def test_the_games_own_name_wins_and_is_made_speakable(self):
        self.assertEqual(ship_name("anaconda_mkii", "Anaconda Mk II"), "Anaconda Mark 2")
        self.assertEqual(ship_name("x", "Cobra MkIII"), "Cobra Mark 3")
        self.assertEqual(ship_name("x", "Krait Phantom"), "Krait Phantom")

    def test_empty_and_damaged_input(self):
        self.assertEqual(ship_name(None), "")
        self.assertEqual(ship_name(""), "")
        self.assertEqual(ship_name(123), "123")

    def test_table_can_be_extended(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ships.json"
            path.write_text(json.dumps({"ships": {"anaconda_mkii": "Anaconda Two"}}))
            ships.reload(path)
            try:
                self.assertEqual(ship_name("anaconda_mkii"), "Anaconda Two")
            finally:
                ships.reload()
        self.assertEqual(ship_name("anaconda_mkii"), "Anaconda Mark 2")


class ThroughTheJournal(unittest.TestCase):
    def test_swapping_to_a_new_ship_and_targeting_one(self):
        processor, _bus, heard = make_processor()
        processor.handle_line(json.dumps({"event": "ShipyardSwap", "ShipType": "anaconda_mkii", "ShipType_Localised": "Anaconda Mk II"}))
        self.assertEqual(heard[-1].data["ship"], "Anaconda Mark 2")
        processor.handle_line(json.dumps({"event": "ShipyardSwap", "ShipType": "anaconda_mkii"}))
        self.assertEqual(heard[-1].data["ship"], "Anaconda Mark 2")
        processor.handle_line(json.dumps({"event": "ShipyardBuy", "ShipType": "anaconda_mkii", "ShipPrice": 1}))
        self.assertEqual(heard[-1].data["ship"], "Anaconda Mark 2")
        processor.handle_line(json.dumps({"event": "ShipTargeted", "TargetLocked": True, "ScanStage": 1, "Ship": "anaconda_mkii",
                                          "Ship_Localised": "Anaconda Mk II"}))
        self.assertEqual(heard[-1].data["Ship"], "Anaconda Mark 2")


if __name__ == "__main__":
    unittest.main()


class NotShips(unittest.TestCase):
    """The Nomad and the SRVs are vehicles, never her favourite ship."""

    def test_vehicles_are_not_ships(self):
        for name in ("Nomad", "nomad", "TestBuggy", "SRV Scarab", "combat_multicrew_srv_01", "", None):
            self.assertFalse(ships.is_ship(name), name)
        for name in ("anaconda", "CobraMkIII", "type9_military", "Python_NX", "Anaconda"):
            self.assertTrue(ships.is_ship(name), name)

    def test_the_nomad_earns_no_points_and_an_old_file_is_cleaned(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from personality.favourite_ship import FavouriteShip
        folder = Path(tempfile.mkdtemp())
        path = folder / "favourite_ship.json"
        path.write_text(json.dumps({"points": {"nomad": 40.0, "anaconda": 25.0}, "labels": {"nomad": "Nomad", "anaconda": "Anaconda"},
                                    "favourite": "nomad"}), encoding="utf-8")
        state = SimpleNamespace(ship="nomad", ship_model=None, favourite_ship=None)
        fav = FavouriteShip(lambda: state, path=path)
        self.assertEqual(fav.favourite, "anaconda")            # the Nomad is dropped; the best real ship is next
        self.assertNotIn("nomad", fav.points)
        fav.add(5)                                              # flying the Nomad: no points
        self.assertNotIn("nomad", fav.points)
        state.ship = "python"
        fav.add(5)
        self.assertEqual(fav.points["python"], 5)
