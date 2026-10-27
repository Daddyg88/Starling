"""Hearing accents: sound-alike repair, her name with an accent, the recogniser hint and the model choices."""

import tempfile
import unittest
from pathlib import Path

from control.learning import VoiceLearning
from control.matcher import Matcher
from stt.faster_whisper_stt import FasterWhisperSTT, HINT
from stt.hints import MAX_CHARS, build_hint
from stt.sounds import same_sound, sound_key
from stt.wake import parse_wake
from ui import settings_model


class Sounds(unittest.TestCase):
    def test_accent_pairs_sound_alike(self):
        for a, b in (("plot", "blot"), ("starling", "sterling"), ("starling", "shtarling"), ("open", "opun"),
                     ("three", "tree"), ("galaxy", "kalaxy")):
            self.assertTrue(same_sound(a, b), (a, b))

    def test_different_words_stay_different(self):
        for a, b in (("gear", "map"), ("scoop", "fuel"), ("open", "close"), ("raise", "lower")):
            self.assertFalse(same_sound(a, b), (a, b))

    def test_numbers_and_empty(self):
        self.assertEqual(sound_key("100"), "100")
        self.assertEqual(sound_key(""), "")


class SoundRepair(unittest.TestCase):
    def setUp(self):
        self.m = Matcher()

    def test_an_accent_style_mishearing_is_repaired(self):
        for said, command in (("opun the galaxy map", "galaxy_map"), ("kalaxy mab", "galaxy_map"),
                              ("raze the gear", "gear"), ("deploi the scoop", "scoop")):
            found = self.m.match(said)
            self.assertIsNotNone(found, said)
            self.assertEqual(found.command.id, command, said)
            self.assertEqual(found.how, "sound", said)

    def test_the_direction_survives(self):
        up = self.m.match("retrackt gear")
        self.assertEqual((up.command.id, up.intent), ("gear", "off"))

    def test_an_ambiguous_sound_is_not_guessed(self):
        self.assertIsNone(self.m.match("lover the gear"))         # lower, leave and lever all sound like it

    def test_big_actions_are_never_guessed_from_a_sound(self):
        self.assertIsNone(self.m.match("hiperspace"))
        self.assertIsNone(self.m.match("suppercruise"))

    def test_chat_is_not_turned_into_a_command(self):
        for said in ("tell me a joke", "how is the weather today", "what do you think about pizza"):
            self.assertIsNone(self.m.match(said), said)

    def test_too_many_repairs_are_refused(self):
        self.assertIsNone(self.m.sound_repair("opun kalaxy mab"))

    def test_a_known_word_is_left_alone(self):
        self.assertIsNone(self.m.sound_repair("open galaxy map"))

    def test_a_sound_match_is_remembered_after_it_repeats(self):
        folder = tempfile.mkdtemp()
        learning = VoiceLearning(Path(folder) / "learn.json")
        m = Matcher(learning=learning)
        for _ in range(2):
            m.match("opun the galaxy map")
        found = m.match("opun the galaxy map")
        self.assertEqual(found.how, "learned")
        self.assertEqual(found.command.id, "galaxy_map")
        self.assertIn("open galaxy map", learning.top_phrases())


class WakeWord(unittest.TestCase):
    def test_accented_names_count(self):
        for said in ("Sterling open the map", "Shtarling open the map", "Starlin open the map", "Stalling open the map"):
            heard, rest = parse_wake(said)
            self.assertTrue(heard, said)
            self.assertEqual(rest, "open the map")

    def test_ordinary_speech_does_not(self):
        for said in ("open the map", "hello there friend", "the weather is nice"):
            self.assertFalse(parse_wake(said)[0], said)


class Hint(unittest.TestCase):
    def test_name_first_and_short(self):
        text = build_hint("Starling", ["open galaxy map", "lower gear"])
        self.assertTrue(text.startswith("Starling."))
        self.assertIn("open galaxy map.", text)
        self.assertLessEqual(len(text), MAX_CHARS)
        self.assertIn("neutron route", text)

    def test_many_phrases_still_fit(self):
        text = build_hint("A very long wake phrase indeed", ["some quite long player phrase number %d" % i for i in range(40)])
        self.assertLessEqual(len(text), MAX_CHARS)

    def test_the_recogniser_gets_the_hint_and_beam(self):
        seen = {}

        class Segment:
            text = " open the map "

        class Model:
            def transcribe(self, audio, **kwargs):
                seen.update(kwargs)
                return [Segment()], None

        small = FasterWhisperSTT("small.en", model_factory=Model)
        small.hint_words = lambda: ("Starling", ["lower gear"])
        self.assertEqual(small.transcribe([0.0]), "open the map")
        self.assertIn("lower gear.", seen["initial_prompt"])
        self.assertEqual(seen["beam_size"], 3)
        tiny = FasterWhisperSTT("tiny.en", model_factory=Model)
        tiny.transcribe([0.0])
        self.assertEqual(seen["beam_size"], 1)
        self.assertEqual(seen["initial_prompt"], HINT)

    def test_a_broken_hint_never_stops_listening(self):
        stt = FasterWhisperSTT("tiny.en", model_factory=object)
        stt.hint_words = lambda: 1 / 0
        self.assertEqual(stt.current_hint(), HINT)


class Models(unittest.TestCase):
    def test_a_strong_model_is_offered(self):
        self.assertIn("medium.en", [value for _label, value in settings_model.LISTEN_QUALITY])


if __name__ == "__main__":
    unittest.main()


class OneWordTests(unittest.TestCase):
    def test_a_name_on_its_own_is_never_repaired_into_a_command(self):
        from control.matcher import Matcher
        matcher = Matcher()
        for name in ("Oli", "Ali", "Milo", "Rex"):
            self.assertIsNone(matcher.match(name), name)
            self.assertIsNone(matcher.suggest(name), name)
        self.assertIsNotNone(matcher.match("opun the galaxy map"))
