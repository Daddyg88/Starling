import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import diagnostics


class CommanderNameInTheZip(unittest.TestCase):
    def make(self, commander):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "logs").mkdir()
        (tmp / "settings.json").write_text("{}", encoding="utf-8")
        out = diagnostics.make_bundle(tmp / "settings.json", tmp / "logs", tmp / "data", "9.9.9", tmp / "out", commander=commander)
        with zipfile.ZipFile(out) as bundle:
            return json.loads(bundle.read("about.json"))

    def test_the_commander_is_the_first_thing_in_about(self):
        about = self.make("CMDR Test")
        self.assertEqual(list(about)[0], "commander")
        self.assertEqual(about["commander"], "CMDR Test")
        self.assertEqual(about["version"], "9.9.9")

    def test_without_a_name_it_says_so(self):
        for missing in (None, "", "  "):
            self.assertIn("unknown", self.make(missing)["commander"])
