import unittest

from tts.pronounce import prepare


class DecimalTests(unittest.TestCase):
    def test_point_is_said(self):
        self.assertEqual(prepare("A 79.9 light year hop."), "A 79 point 9 light year hop.")
        self.assertEqual(prepare("About 8.1 million credits."), "About 8 point 1 million credits.")

    def test_digits_after_point_one_by_one(self):
        self.assertEqual(prepare("Gravity is 1.25."), "Gravity is 1 point 2 5.")

    def test_ids_and_versions_and_thousands_untouched(self):
        for text in ("DSSA #21.02.002 now", "version 0.96.3", "1,662 light years", "Done. 4 jumps.", "at 5."):
            self.assertEqual(prepare(text), text)

    def test_no_double_work(self):
        once = prepare("It is 7.9 and Fonticulua.")
        self.assertEqual(prepare(once), once)


class UnitTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(prepare("at least 500 m away"), "at least 500 metres away")
        self.assertEqual(prepare("2 km out"), "2 kilometres out")
        self.assertEqual(prepare("pulls 1.2 g"), "pulls 1 point 2 gee")

    def test_not_other_words(self):
        self.assertEqual(prepare("5 minutes and 3 more"), "5 minutes and 3 more")


class WordTests(unittest.TestCase):
    def test_latin_respelt_for_every_voice(self):
        self.assertEqual(prepare("Stratum Tectonicas"), "Stratum tec tonic ahs")
        self.assertIn("terra formable", prepare("a terraformable world"))

    def test_metres_only_for_the_australian_voice(self):
        self.assertEqual(prepare("100 metres", ""), "100 metres")
        self.assertEqual(prepare("100 metres", "melo_en_au"), "100 meeters")

    def test_pause_mark_and_empty(self):
        self.assertEqual(prepare("One.||Two."), "One.||Two.")
        self.assertEqual(prepare(""), "")
        self.assertIsNone(prepare(None))


if __name__ == "__main__":
    unittest.main()
