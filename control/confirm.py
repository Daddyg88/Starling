"""
"DID YOU MEAN...?" - when she is nearly sure, she asks instead of guessing or ignoring you.

If what she heard is close to a command but not close enough to run safely ("hyperspace jum", "engage the supercrews"), she says
"Did you mean engage supercruise?" and waits a few seconds. Say "yes" (no need to say her name) and she does it, and
remembers that this is how you say it; say "no" and she drops it. Anything else cancels the question and is treated as a new
sentence. Big actions (jumping, supercruise) are only ever done after a clear yes, and are never remembered as shortcuts.
"""
import re

WINDOW_SECONDS = 15.0              # her question can take 3 or 4 seconds to say, so the answer window starts to feel short at 10
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
        if self._yes_and_the_command(said):
            return "yes"
        self.pending = None
        return None

    def _yes_and_the_command(self, said):
        """'yes, target the shield generator' while she is asking 'say yes if you meant sub target shield generator': a yes word followed by
        (nearly) the words she asked about counts as a yes. 'yes' followed by something else does not."""
        words = said.split()
        if len(words) < 2 or words[0] not in ("yes", "yeah", "yep", "yup", "correct", "sure", "right"):
            return False
        rest = [w for w in words[1:] if w not in ("the", "a", "my", "please")]
        asked = [w for w in tidy(getattr(self.pending[0], "phrase", "") or "").split() if w not in ("the", "a", "my")]
        if not rest or not asked:
            return False
        return sum(1 for w in rest if w in asked) / len(rest) >= 0.75

    def take(self):
        pending, self.pending = self.pending, None
        return pending

    def is_refused(self, heard, phrase):
        return (heard, phrase) in self.refused

    def refuse(self, heard, phrase):
        self.refused.add((heard, phrase))
