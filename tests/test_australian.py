import json
import unittest

from core import paths
from personality.australian import australian_on
from personality.flavour import AUSSIE_PET_CHANCE
from tests.test_flavour import make, texts


def aussie(f, on=True):
    f.settings.set("tts.voice", "melo_en_au" if on else "kokoro_af_heart")
    return f


class AustralianTests(unittest.TestCase):
    def test_only_with_the_australian_voice(self):
        f, d = make()
        self.assertFalse(australian_on(f.settings))
        aussie(f)
        self.assertTrue(australian_on(f.settings))
        f.settings.set("personality.aussie_slang", False)
        self.assertFalse(australian_on(f.settings))

    def test_not_in_info_only_style(self):
        f, d = make(style="info")
        aussie(f)
        self.assertFalse(australian_on(f.settings))

    def test_pools_exist_and_mature_ones_are_marked(self):
        data = json.load(open(paths.VOICEPACKS_DIR / "default" / "aussie.json", encoding="utf-8"))
        for key in ("Aussie_Open", "Aussie_Close", "PetName_Aussie", "Remark_Aussie", "ChitChat_Aussie"):
            self.assertTrue(texts(make()[1], key), key)
        for line in data["Aussie_Open"] + data["Aussie_Close"] + data["PetName_Aussie"]:
            self.assertIsInstance(line, str)

    def test_pet_name_is_australian_only_in_australian_mode(self):
        f, d = make(roll=0.0)
        names = texts(d, "PetName_Aussie")
        aussie(f, on=False)
        self.assertNotIn(f._pet_name("Friendly"), names)
        aussie(f)
        self.assertIn(f._pet_name("Friendly"), names)

    def test_remark_is_australian_only_in_australian_mode(self):
        f, d = make(roll=0.0)
        pool = texts(d, "Remark_Aussie")
        aussie(f, on=False)
        self.assertNotIn(f._remark("Friendly"), pool)
        aussie(f)
        self.assertIn(f._remark("Friendly"), pool)

    def test_apply_adds_a_short_word_only_in_australian_mode(self):
        f, d = make(roll=0.0)
        words = texts(d, "Aussie_Open") | texts(d, "Aussie_Close")
        aussie(f, on=False)
        out = f.apply("Docking complete.", "normal")
        self.assertFalse(any(w in out for w in words))
        aussie(f)
        out = f.apply("Docking complete.", "normal")
        self.assertTrue(any(w in out for w in words), out)

    def test_chitchat_pool_only_when_on(self):
        from tests.test_chitchat import Base
        self.assertTrue(texts(make()[1], "ChitChat_Aussie"))


if __name__ == "__main__":
    unittest.main()
