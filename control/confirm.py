"""
"DID YOU MEAN...?" - when she is nearly sure, she asks instead of guessing or ignoring you.

If what she heard is close to a command but not close enough to run safely ("hyperspace jum", "engage the supercrews"), she says
"Did you mean engage supercruise?" and waits a few seconds. Say "yes" (no need to say her name) and she does it, and
remembers that this is how you say it; say "no" and she drops it. Anything else cancels the question and is treated as a new
sentence. Big actions (jumping, supercruise) are only ever done after a clear yes, and are never remembered as shortcuts.
"""
import re

WINDOW_SECONDS = 10.0
YES = {"yes", "yeah", "yep", "yup", "aye", "correct", "right", "thats right", "thats it", "thats the one", "that one", "exactly", "do it",
       "go ahead", "please", "yes please", "sure", "affirmative", "yes thats right", "yes do it", "yeah thats right", "yeah do it",
       "yes it is", "yes i did", "that is right", "ok", "okay"}
NO = {"no", "nope", "nah", "negative", "cancel", "never mind", "nevermind", "forget it", "thats not it", "not that", "wrong", "no thanks",
      "no thank you", "no i didnt", "no stop", "stop", "dont"}


def tidy(text):
    text = re.sub(r"['’]", "", (text or "").lower())
    text = re.sub(r"[^a-z ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^(?:hey |hi |ok |okay )?(?:starling )", "", text) or text


class Confirmer:
    def __init__(self, clock):
        self.clock = clock
        self.pending = None            # (Match, what was heard, expires)
        self.refused = set()           # (heard, phrase) you said no to: not asked again

    def ask(self, match, heard):
        self.pending = (match, heard, self.clock() + WINDOW_SECONDS)

    def active(self):
        if self.pending is not None and self.clock() > self.pending[2]:
            self.pending = None
        return self.pending is not None

    def answer(self, text):
        """'yes', 'no' or None (neither: the question is dropped and the sentence is a new one)."""
        if not self.active():
            return None
        said = tidy(text)
        if said in YES:
            return "yes"
        if said in NO:
            return "no"
        self.pending = None
        return None

    def take(self):
        pending, self.pending = self.pending, None
        return pending

    def is_refused(self, heard, phrase):
        return (heard, phrase) in self.refused

    def refuse(self, heard, phrase):
        self.refused.add((heard, phrase))
