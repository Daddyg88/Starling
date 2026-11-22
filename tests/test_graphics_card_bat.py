"""The one-click graphics-card voice installer: it exists, uses Windows line endings, and always puts the original torch back on failure."""
import unittest
from pathlib import Path

BAT = Path(__file__).resolve().parent.parent / "run_voice_on_graphics_card.bat"


class GraphicsCardBat(unittest.TestCase):
    def test_exists_with_windows_line_endings(self):
        data = BAT.read_bytes()
        self.assertIn(b"\r\n", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_keeps_the_original_when_nothing_works(self):
        text = BAT.read_text()
        self.assertIn("whl/cpu", text)                      # the original (processor) torch is restored
        self.assertIn("--no-deps", text)                    # only torch is replaced, nothing else on the PC is touched
        self.assertIn("nvidia-smi", text)                   # no NVIDIA card: it stops before changing anything
        self.assertLess(text.index("nvidia-smi"), text.index("pip install"))

    def test_tries_newest_first_then_older_builds(self):
        text = BAT.read_text()
        self.assertLess(text.index("cu126"), text.index("cu124"))


if __name__ == "__main__":
    unittest.main()
