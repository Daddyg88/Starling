"""Canonn archive knowledge: the build tool (opening only, no Merchandise, no stale announcements) and the shipped file."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_canonn_knowledge as tool  # noqa: E402
from personality.knowledge import Knowledge  # noqa: E402
from personality.smalltalk import clean  # noqa: E402


def article(folder, slug, title, body, section="codex", cats=("Xenology",)):
    d = Path(folder) / "content" / "articles" / slug
    d.mkdir(parents=True)
    (d / "article.json").write_text(json.dumps({"title": title, "slug": slug, "section": section, "author": "Someone",
                                                "categories": [{"category": c, "subs": []} for c in cats]}), encoding="utf-8")
    (d / "body.html").write_text(body, encoding="utf-8")


LONG = ("<p>Glowing Fungus Pods grow in the dark of the far side of cold moons. They give off a pale light when a ship comes near and nobody knows why. "
        "Scanning them twice gives different readings. This third sentence is here to be cut off long before the end of the article is reached by anybody at all.</p>"
        "<p>More text that should never be copied: " + "blah " * 200 + "</p>")


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        article(self.tmp.name, "glowing-fungus-pods", "Glowing Fungus Pods", LONG)
        article(self.tmp.name, "canonn-mug", "Canonn Mug", LONG, cats=("Merchandise",))
        article(self.tmp.name, "old-thing", "Old Thing Here", LONG, cats=("Obsolete/Incomplete",))
        article(self.tmp.name, "vote-now", "Vote For Station Names", LONG, section="event")
        article(self.tmp.name, "tau", "Tau", LONG)
        article(self.tmp.name, "exploration", "Exploration", LONG)
        article(self.tmp.name, "short", "Tiny Page", "<p>Too short.</p>")
        self.entries, self.total = tool.build(Path(self.tmp.name) / "content" / "articles")

    def test_only_the_right_articles_are_kept(self):
        sources = [e["src"] for e in self.entries]
        self.assertEqual(sources, ["https://science.canonn.tech/codex/glowing-fungus-pods"])

    def test_only_a_short_opening_is_kept_and_canonn_is_credited(self):
        text = self.entries[0]["a"]
        self.assertLess(len(text), 520)
        self.assertNotIn("blah", text)
        self.assertIn("Canonn research archive", text)
        self.assertIn("xenology", text)

    def test_text_is_fit_to_be_spoken(self):
        spoken = tool.speakable("Go to https://example.com now (see note) at -45.8204, 66.8409 & see #3")
        self.assertNotIn("http", spoken)
        self.assertNotIn("45.8", spoken)
        self.assertNotIn("(", spoken)
        self.assertIn("and", spoken)

    def test_keys_are_the_title_without_little_words(self):
        self.assertEqual(tool.keys_for("The Guardian Ruins")[0], ["guardian", "ruin"])
        self.assertEqual(tool.keys_for("Site 94")[0], ["site", "94"])
        self.assertEqual(tool.keys_for("Tau"), [])
        self.assertIn(["brain", "tree"], tool.keys_for("A Study on the Brain Trees"))


class ShippedFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "config" / "knowledge" / "canonn.json").read_text(encoding="utf-8"))
        cls.knowledge = Knowledge()

    def test_it_is_a_sensible_size_and_credits_canonn(self):
        self.assertGreater(len(self.data["entries"]), 500)
        self.assertLess((ROOT / "config" / "knowledge" / "canonn.json").stat().st_size, 600_000)
        self.assertIn("Canonn", self.data["_help"])
        for entry in self.data["entries"]:
            self.assertLess(len(entry["a"]), 520)

    def test_no_merchandise(self):
        for entry in self.data["entries"]:
            self.assertNotIn("merchandise", entry["src"])
            self.assertNotIn("merchandise", " ".join(entry["k"][0]))

    def test_she_answers_from_it(self):
        reply = self.knowledge.lookup(clean("what is a bullet mollusc"))
        self.assertIsNotNone(reply)
        self.assertIn("Bullet Mollusc", reply[1])
        self.assertIn("Canonn research archive", reply[1])

    def test_chat_is_not_hijacked(self):
        for said in ("how are you today", "what is the weather like", "i love pizza", "what is exploration", "can you hear me", "where is the carrier"):
            found = self.knowledge.lookup(clean(said))
            self.assertTrue(found is None or "Canonn research archive" not in found[1], said)


if __name__ == "__main__":
    unittest.main()
