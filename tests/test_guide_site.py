"""The guide website (tools/build_guide.py) must list every voice command, and every example in it must really work."""
import importlib.util
import unittest
from pathlib import Path

from control import catalog
from control.matcher import Matcher

SPEC = importlib.util.spec_from_file_location("build_guide", Path(__file__).resolve().parent.parent / "tools" / "build_guide.py")
GUIDE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUIDE)


class GuideSite(unittest.TestCase):
    def test_every_command_is_in_the_guide(self):
        page = GUIDE.build()
        for command in catalog.CATALOG:
            self.assertIn(GUIDE.html.escape(GUIDE.name(command)), page, command.id)

    def test_every_example_is_understood(self):
        matcher = Matcher()
        for _gid, _title, _intro, ids in GUIDE.GROUPS:
            for command_id in ids:
                command = GUIDE.C[command_id]
                for example in GUIDE.examples(command):
                    match = matcher.match(example)
                    self.assertIsNotNone(match, example)
                    self.assertEqual(match.command.id, command_id, example)

    def test_brain_examples_are_understood(self):
        from personality.brain import load_intents, strip_address
        from personality.smalltalk import clean
        intents = load_intents()

        def key(text):
            tidy = strip_address(clean(text))
            for item, patterns in intents:
                if any(p.search(tidy) for p in patterns):
                    return item["key"]
        self.assertEqual(key("I want to go merit mining"), "Brain_Merit")
        self.assertEqual(key("Where is the nearest black market?"), "Brain_Service")
        self.assertEqual(key("Where can I buy platinum?"), "Brain_BuyPrice")

    def test_page_is_a_whole_web_page(self):
        page = GUIDE.build()
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("</body></html>", page)
        self.assertNotIn("{{", page)


if __name__ == "__main__":
    unittest.main()
