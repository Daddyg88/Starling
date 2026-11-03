import unittest
from types import SimpleNamespace
from unittest import mock

from stt.listener import is_garbage


class GarbageTests(unittest.TestCase):
    def test_repeated_sound_is_garbage(self):
        self.assertTrue(is_garbage("-".join(["P"] * 44)))
        self.assertTrue(is_garbage("Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you."))

    def test_real_sentences_are_not(self):
        self.assertFalse(is_garbage("Computer, plot me a route to the nearest DSSA."))
        self.assertFalse(is_garbage("Full."))
        self.assertFalse(is_garbage("No no no no no no no no please stop it"))


class RouteReadyDssaTests(unittest.TestCase):
    def test_voicepack_has_the_line(self):
        import json
        from core import paths
        data = json.load(open(paths.ROOT / "voicepacks" / "default" / "route.json", encoding="utf-8")) \
            if hasattr(paths, "ROOT") else json.load(open("voicepacks/default/route.json", encoding="utf-8"))
        self.assertIn("RouteReadyDssa", data)
        for line in data["RouteReadyDssa"]:
            self.assertIn("{carrier}", line)


if __name__ == "__main__":
    unittest.main()
