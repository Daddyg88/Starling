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
