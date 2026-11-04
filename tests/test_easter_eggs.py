import re
import unittest
from pathlib import Path

from control import catalog, easter_eggs

ROOT = Path(__file__).resolve().parent.parent


class Secrets(unittest.TestCase):
    def test_phrase_becomes_deploy_hardpoints(self):
        for said in ("Show 'em your tits", "show them your tits!", "show em ur tits", "Starling, show the lads your tits"):
            self.assertEqual(easter_eggs.rewrite(said), "deploy hardpoints", said)
        for said in ("show me the map", "deploy hardpoints", "", None):
            self.assertIsNone(easter_eggs.rewrite(said))

    def test_never_listed_anywhere(self):
        everything = repr(catalog.COMMANDS if hasattr(catalog, "COMMANDS") else vars(catalog)).lower()
        self.assertNotIn("tits", everything)
        for path in list((ROOT / "tools").glob("*.html")) + [ROOT / "README.md", ROOT / "docs" / "PHASE6_GUIDE.md"]:
            self.assertNotIn("your tits", path.read_text(encoding="utf-8").lower(), path.name)
        for path in (ROOT / "config").glob("*.json"):
            self.assertNotIn("your tits", path.read_text(encoding="utf-8").lower(), path.name)


if __name__ == "__main__":
    unittest.main()
