import unittest

from tts.pronounce import prepare


class DecimalTests(unittest.TestCase):
    def test_point_is_said(self):
        self.assertEqual(prepare("A 79.9 light year hop."), "A 79 point 9 light year hop.")
        self.assertEqual(prepare("About 8.1 million credits."), "About 8 point 1 million credits.")

    def test_digits_after_point_one_by_one(self):
        self.assertEqual(prepare("Gravity is 1.25."), "Gravity is 1 point 2 5.")

    def test_ids_and_versions_and_thousands_untouched(self):
        for text in ("Carrier #21.02.002 now", "version 0.96.3", "1,662 light years", "Done. 4 jumps.", "at 5."):
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


class AussieAndBrokenUpWords(unittest.TestCase):
    """0.96.42: Ben heard "Geee day" for G'day, and wanted supercruise / exobiology broken up."""

    def test_gday_is_said_guh_day_with_either_apostrophe(self):
        self.assertEqual(prepare("G'day mate"), "guh day mate")
        self.assertEqual(prepare("Well g’day"), "Well guh day")

    def test_long_game_words_are_broken_up(self):
        self.assertEqual(prepare("Dropping out of supercruise."), "Dropping out of super cruise.")
        self.assertEqual(prepare("Exobiology scan complete."), "exo biology scan complete.")

    def test_ordinary_words_are_left_alone(self):
        self.assertEqual(prepare("Have a good day, today."), "Have a good day, today.")


class YearsOrdinalsCodes(unittest.TestCase):
    def test_years(self):
        from tts.pronounce import prepare
        self.assertIn("nineteen ninety-four", prepare("Founded in 1994."))
        self.assertIn("thirty-one twenty-five", prepare("They met in 3125."))
        self.assertIn("thirty-three oh nine", prepare("It fell in 3309."))

    def test_quantities_untouched(self):
        from tts.pronounce import prepare
        self.assertIn("1500 credits", prepare("Pays 1500 credits a tonne."))

    def test_ordinals(self):
        from tts.pronounce import prepare
        self.assertIn("sixteenth", prepare("the 16th of May"))
        self.assertIn("twenty-first", prepare("the 21st"))

    def test_system_code_and_acronyms(self):
        from tts.pronounce import prepare
        self.assertIn("N L dash N, C 2 3 dash 4", prepare("NL-N C23-4"))
        self.assertIn("S R V", prepare("the SRV"))

    def test_real_system_names_have_a_lowercase_mass_code(self):
        from tts.pronounce import prepare
        self.assertEqual(prepare("Wregoe YU-H b51-7"), "Wregoe Y U dash H, B 5 1 dash 7")
        self.assertEqual(prepare("Eurybia Blu Hypa ZV-T d3-98 A 2"), "Eurybia Blu Hypa Z V dash T, D 3 dash 9 8 A 2")
        self.assertEqual(prepare("Sector YU-O b6"), "Sector Y U dash O, B 6")


class SaluteTests(unittest.TestCase):
    def test_o7_is_said_oh_seven(self):
        self.assertEqual(prepare("o7 Commander"), "oh seven Commander")
        self.assertEqual(prepare("O7, Ann."), "oh seven, Ann.")
        self.assertEqual(prepare("Salute received. o7, Gav."), "Salute received. oh seven, Gav.")

    def test_only_the_salute(self):
        for text in ("Pro7 rocks", "room 07", "a o70 thing", "foo7"):
            self.assertEqual(prepare(text), text)
