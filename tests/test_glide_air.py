import unittest

from events.scan import atmosphere_phrase
from personality import line_keys


class Event:
    def __init__(self, data):
        self.name = "GlideStarted"
        self.data = data


class AtmosphereTests(unittest.TestCase):
    def test_phrases(self):
        self.assertEqual(atmosphere_phrase({"Atmosphere": "thin argon atmosphere", "AtmosphereType": "Argon"}), "a thin argon atmosphere")
        self.assertEqual(atmosphere_phrase({"Atmosphere": "hot thick ammonia atmosphere"}), "a hot thick ammonia atmosphere")
        self.assertEqual(atmosphere_phrase({"Atmosphere": "", "AtmosphereType": "None"}), "no atmosphere")
        self.assertEqual(atmosphere_phrase({"Atmosphere": "suitable for water based life", "AtmosphereType": "EarthLike"}),
                         "an atmosphere that is suitable for water based life")
        self.assertIsNone(atmosphere_phrase({"StarType": "K"}))

    def test_oxygen_is_named_when_there_is_some(self):
        scan = {"Atmosphere": "thin nitrogen atmosphere", "AtmosphereComposition": [{"Name": "Nitrogen", "Percent": 80.0}, {"Name": "Oxygen", "Percent": 19.5}]}
        self.assertEqual(atmosphere_phrase(scan), "a thin nitrogen atmosphere, with 19.5 percent oxygen")
        self.assertEqual(atmosphere_phrase({"Atmosphere": "thin oxygen atmosphere", "AtmosphereComposition": [{"Name": "Oxygen", "Percent": 100.0}]}),
                         "a thin oxygen atmosphere")
        self.assertEqual(atmosphere_phrase({"Atmosphere": "thin argon atmosphere", "AtmosphereComposition": [{"Name": "Oxygen", "Percent": 0.1}]}), "a thin argon atmosphere")


class KeysTests(unittest.TestCase):
    def test_air_keys_first_when_known(self):
        keys = line_keys.keys_for(Event({"temperature": 200, "gravity": "0.40", "atmosphere": "no atmosphere"}))
        self.assertEqual(keys[0], "GlideStarted_Air")
        self.assertIn("GlideStarted_Info", keys)

    def test_heavy_with_air(self):
        keys = line_keys.keys_for(Event({"temperature": 200, "gravity": "2.50", "heavy": True, "atmosphere": "a thick atmosphere"}))
        self.assertEqual(keys[:2], ["GlideStarted_HeavyAir", "GlideStarted_Air"])

    def test_no_air_known_is_as_before(self):
        keys = line_keys.keys_for(Event({"temperature": 200, "gravity": "0.40"}))
        self.assertEqual(keys, ["GlideStarted_Info", "GlideStarted"])
        keys = line_keys.keys_for(Event({"temperature": 200, "gravity": "3.0", "heavy": True}))
        self.assertEqual(keys[0], "GlideStarted_Heavy")


if __name__ == "__main__":
    unittest.main()
