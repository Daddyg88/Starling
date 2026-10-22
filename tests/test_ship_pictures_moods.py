"""Ship pictures, and the two new moods (Infatuated above Close, Upset below Frustrated)."""
import json
import tempfile
import unittest
from pathlib import Path

from core import paths
from personality import moods
from personality.dialogue import DialogueManager
from personality.mood_engine import BANDS, MoodEngine
from tools import get_ship_pictures
from ui import portraits, ship_pictures


class ShipPictureTests(unittest.TestCase):
    def test_names_become_the_same_slug(self):
        self.assertEqual(ship_pictures.slug("Cobra MkIII"), "cobra3")
        self.assertEqual(ship_pictures.slug("Cobra Mark 3"), "cobra3")
        self.assertEqual(ship_pictures.slug("Type-9 Heavy"), "type9heavy")

    def test_finds_by_game_code_and_by_name(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "cobra3.png").write_bytes(b"x")
            (Path(folder) / "anaconda.jpg").write_bytes(b"x")
            self.assertEqual(ship_pictures.picture_for("cobramkiii", folders=[folder]).name, "cobra3.png")
            self.assertEqual(ship_pictures.picture_for("", "Anaconda", folders=[folder]).name, "anaconda.jpg")
            self.assertIsNone(ship_pictures.picture_for("python", folders=[folder]))

    def test_mk1_wiki_names_match(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "sidewinder1.png").write_bytes(b"x")
            self.assertIsNotNone(ship_pictures.picture_for("sidewinder", folders=[folder]))

    def test_downloader_reads_image_tags(self):
        html = ('<img src="data:image/gif;base64,AAA" alt="x">'
                '<img alt="Anaconda" data-src="https://static.wikia.nocookie.net/elite/images/a/ab/Anaconda.png/revision/latest/scale-to-width-down/185?cb=1">'
                '<img alt="Wiki logo" src="https://static.wikia.nocookie.net/x/logo.png">')
        found = get_ship_pictures.find_pictures(html)
        self.assertEqual([name for name, _ in found], ["Anaconda"])
        self.assertNotIn("scale-to-width", found[0][1])


class MoodTests(unittest.TestCase):
    def engine(self):
        return MoodEngine.__new__(MoodEngine)

    def band(self, score, current=None):
        engine = self.engine()
        engine.options = {"frustrated_at": -35, "sarcastic_at": -10, "friendly_at": 10, "close_at": 30,
                          "infatuated_at": 60, "upset_at": -60, "hysteresis": 4}
        return engine._band_for(score, current)

    def test_seven_bands_in_order(self):
        self.assertEqual(BANDS, list(moods.ORDER))

    def test_new_bands_reached_going_up_and_down(self):
        self.assertEqual(self.band(45), "Close")
        self.assertEqual(self.band(60), "Infatuated")
        self.assertEqual(self.band(60, "Close"), "Infatuated")
        self.assertEqual(self.band(-50), "Frustrated")
        self.assertEqual(self.band(-61, "Frustrated"), "Frustrated")    # hysteresis: 4 points past the line going down
        self.assertEqual(self.band(-65, "Frustrated"), "Upset")
        self.assertEqual(self.band(-61, "Upset"), "Upset")
        self.assertEqual(self.band(-58, "Upset"), "Frustrated")         # back up the moment she crosses the line

    def test_new_moods_use_the_older_lines_and_their_own(self):
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        close = len(dialogue.pool("FSDJump", "Close"))
        self.assertGreaterEqual(len(dialogue.pool("FSDJump", "Infatuated")), close + 1)
        self.assertGreaterEqual(len(dialogue.pool("FSDJump", "Upset")), len(dialogue.pool("FSDJump", "Frustrated")) + 1)

    def test_every_own_line_has_the_placeholders_the_old_ones_use(self):
        data = json.load(open(Path(__file__).resolve().parent.parent / "voicepacks/default/moods.json", encoding="utf-8"))
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertTrue(key.rsplit("_", 1)[1] in ("Infatuated", "Upset"), key)
            self.assertTrue(all(isinstance(line, str) and line for line in lines))

    def test_portrait_falls_back_to_the_parent_mood(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "Close.png").write_bytes(b"x")
            (Path(folder) / "Neutral.png").write_bytes(b"x")
            self.assertEqual(portraits.portrait_for("Infatuated", folder).name, "Close.png")
            self.assertEqual(portraits.portrait_for("Upset", folder).name, "Neutral.png")


if __name__ == "__main__":
    unittest.main()
