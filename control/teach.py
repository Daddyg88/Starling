"""TEACH HER: "I meant target power plant" and "what did you miss?".

When she did not understand a sentence she keeps it (control/learning.py). Say what you meant straight afterwards:

    "I meant lower the landing gear"      -> she does it, and next time that mishearing means it, at once
    "what did you miss" / "what didn't you catch"   -> she reads out the last few sentences she could not understand

Safety: only ordinary commands are taught (never the big "strict" actions like jumping), the sentence you name must really be one of her
commands (exact or very close), and it only works for about 5 minutes after the miss.
"""
import re
import time

from control.confirm import tidy

MEANT = re.compile(r"^(?:i meant|i mean|i said|what i said was|that meant|that means|it meant|it means|what i meant was)\s+(.+)$")
ASK = re.compile(r"\b(?:what did you (?:miss|not catch|not understand|not get)|what didnt you (?:catch|understand|get)|what have you missed|what did you not hear)\b")
WINDOW_SECONDS = 300.0


class TeachHelper:
    def __init__(self, runner_provider, clock=time.monotonic):
        self.runner_provider = runner_provider
        self.clock = clock

    def try_handle(self, text):
        said = tidy(text)
        if not said:
            return None
        runner = self.runner_provider()
        learning = getattr(getattr(runner, "matcher", None), "learning", None)
        if learning is None:
            return None
        if ASK.search(said):
            found = learning.recent_misses(3)
            if not found:
                return "I haven't missed anything lately."
            return "I missed: " + "; ".join("'%s'" % h for h in found) + ". Say 'I meant', then the command, to teach me."
        found = MEANT.match(said)
        if not found:
            return None
        last = learning.last_miss
        if last is None or self.clock() - last[1] > WINDOW_SECONDS:
            return None                                   # nothing recent to teach: let it go on as an ordinary sentence
        heard, meant = last[0], found.group(1)
        match = runner.matcher.match(meant) or runner.matcher.suggest(meant)
        if match is None or match.command.strict:
            return "I don't know a command like that, so I can't learn it."
        learning.teach(heard, match.phrase)
        learning.last_miss = None
        runner.run_text(match.phrase, speak_unknown=False)
        return "Got it. When I hear '%s' I'll know you mean %s." % (heard, match.phrase)
