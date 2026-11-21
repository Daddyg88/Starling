"""'live' (liv, to reside) and 'live' (lyve, broadcast), and 'favourite' (0.96.127)."""

import unittest

from tts import pronounce


def say(text, voice=""):
    pronounce.reload()
    return pronounce.prepare(text, voice)


class LiveWordTests(unittest.TestCase):
    def test_the_verb_is_liv(self):
        self.assertEqual(say("I live in London."), "I liv in London.")
        self.assertEqual(say("Where do you live?"), "Where do you liv?")
        self.assertEqual(say("They live on the carrier."), "They liv on the carrier.")
        self.assertEqual(say("Do you want to live forever?"), "Do you want to liv forever?")

    def test_the_adjective_is_lyve(self):
        self.assertEqual(say("We are going live now."), "We are going lyve now.")
        self.assertEqual(say("Live music tonight."), "Lyve music tonight.")
        self.assertEqual(say("It is a live stream."), "It is a lyve stream.")

    def test_lives(self):
        self.assertEqual(say("He lives in a station."), "He livz in a station.")
        self.assertEqual(say("Nine lives to save."), "Nine lyvz to save.")

    def test_unclear_is_left_alone_and_other_words_are_safe(self):
        self.assertEqual(say("Live long."), "Live long.")
        self.assertEqual(say("She is alive and delivered the cargo."), "She is alive and delivered the cargo.")
        self.assertEqual(say("a living"), "a living")

    def test_all_voices(self):
        for voice in ("", "melo_en_au", "kokoro_bf_emma"):
            self.assertIn("lyve", say("Going live.", voice))

    def test_favourite(self):
        self.assertEqual(say("My favourite ship."), "My fay-vuh-rit ship.")
        self.assertEqual(say("Your favorites."), "Your fay-vuh-rits.")
        self.assertEqual(say("Favourite colour?"), "Fay-vuh-rit colour?")


if __name__ == "__main__":
    unittest.main()
