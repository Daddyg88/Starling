"""Words spelt one way and said two (0.96.129): read, close, lead, row, bass, tear, desert, content, use, record, buffet."""

import unittest

from tts import pronounce


def say(text, voice=""):
    pronounce.reload()
    return pronounce.prepare(text, voice)


class Heteronyms(unittest.TestCase):
    def check(self, pairs):
        for before, after in pairs:
            self.assertEqual(say(before), after, before)

    def test_read(self):
        self.check([("I once read that cats rule the house.", "I once red that cats rule the house."), ("I've read this.", "I've red this."),
                    ("I read this once.", "I red this once."), ("Have you read it?", "Have you red it?"),
                    ("Read it out to me.", "Read it out to me."), ("I'll read it to you.", "I'll read it to you."),
                    ("I only read the stars.", "I only read the stars.")])

    def test_close(self):
        self.check([("Stay close, Commander.", "Stay cloce, Commander."), ("That was far too close for my liking", "That was far too cloce for my liking"),
                    ("Was it a close one?", "Was it a cloce one?"), ("I keep a close eye on prices.", "I keep a cloce eye on prices."),
                    ("Close the map.", "Cloze the map."), ("I'll close it.", "I'll cloze it."), ("I need to close the scoop.", "I need to cloze the scoop."),
                    ("Closing the galaxy map", "Closing the galaxy map"), ("Scoop closed", "Scoop closed"), ("Close", "Close")])

    def test_lead_row_bass_tear_desert(self):
        self.check([("hot enough to melt lead", "hot enough to melt led"), ("Flight Lead", "Flight Leed"), ("the lead singer", "the lead singer"),
                    ("days in a row", "days in a roe"), ("heavy bass and a slow beat", "heavy base and a slow beat"),
                    ("tear it apart", "tare it apart"), ("a broad, tear-shaped shield", "a broad, teer-shaped shield"), ("the largest desert", "the largest dez-ert")])

    def test_content_use_record_buffet(self):
        self.check([("Cats purr when they are content", "Cats purr when they are kun-tent"), ("Poor content", "Poor content"),
                    ("Either way, it's content", "Either way, it's content"), ("It's no use leaving it", "It's no yoos leaving it"),
                    ("Use it", "Use it"), ("I'm used to it", "I'm yoost to it"), ("I used them for the first time", "I used them for the first time"),
                    ("I'll record it", "I'll ri-cord it"), ("Let the record show", "Let the record show"), ("a fucking buffet", "a fucking buh-fay")])

    def test_used_to_only_when_it_means_the_habit(self):
        self.check([("A unit used to measure sound.", "A unit used to measure sound."), ("It's used to thicken sauces.", "It's used to thicken sauces."),
                    ("We could get used to this.", "We could get yoost to this."), ("She used to read to me.", "She yoost to read to me.")])

    def test_every_voice_and_nothing_breaks(self):
        for voice in ("", "melo_en_au", "kokoro_bf_emma"):
            self.assertEqual(say("Days in a row.", voice), "Days in a roe.")
        self.assertEqual(say(""), "")
        self.assertEqual(say("Nothing to change here."), "Nothing to change here.")


if __name__ == "__main__":
    unittest.main()
