"""Voice commands: "be quiet", "shut up", "that's enough", and "you can talk again".

"Starling, please be quiet" stops her talking AT ONCE (a safety warning is never cut off) and keeps her quiet for a while (Settings >
Speech > "How long she stays quiet", or whatever you say: "be quiet for five minutes"). While she is quiet only safety warnings and
answers to YOU are spoken; the chatter (call-outs, small talk, facts, questions) waits. "You can talk again" ends it early.
Only whole short sentences count, so "is it quiet in this system?" never silences her."""

import re

from core.logger import get_logger

log = get_logger("quiet")

DEFAULT_MINUTES = 10
MAX_MINUTES = 240
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
           "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60, "an": 60, "a": 1}

_LEAD = r"(?:(?:starling|please|just|now|okay|ok|right|alright|hey|oh|could you|can you|would you|will you|you)\s+)*"
_FOR = r"(?:\s+for\s+(?:a\s+)?(?:(?P<n>\d{1,3}|%s)\s+)?(?P<unit>minutes?|mins?|hours?|hour|bit|while|moment|second|seconds|minute))?" % "|".join(NUMBERS)
_TAIL = r"(?:\s+(?:please|now|for me|thank you|thanks|for now|a bit|a while))*"
_QUIET = re.compile(r"^" + _LEAD + r"(?:"
                    r"(?:be |go |keep |stay |get )?(?:quiet|quite|silent|still|hushed)(?: mode)?"
                    r"|hush|silence|pipe down|zip it|zip your lip|zip your lips|enough|enough now"
                    r"|(?:shut up|shut it|shut your mouth|shut your trap)"
                    r"|(?:stop|quit|cease) (?:talking|speaking|chatting|yapping|babbling|rambling|chattering|the chatter|the noise)"
                    r"|(?:no more|enough) (?:talking|chatter|chat|noise|babbling)"
                    r"|(?:thats|that is|thats) enough"
                    r"|give me (?:some )?(?:peace|quiet|silence|a minute|a moment|a break)"
                    r"|mute yourself|go mute)"
                    + _TAIL + _FOR + _TAIL + r"$")
_RUDE = re.compile(r"\b(?:shut up|shut it|shut your|pipe down|zip it|zip your)\b")
_BACK = re.compile(r"^" + _LEAD + r"(?:(?:you can |youre allowed to |its ok(?:ay)? to |feel free to )?(?:talk|speak|chat)(?: to me)?(?: again| now| now again)?"
                   r"|carry on(?: talking)?|go on|go ahead|unmute(?: yourself)?|im back|i am back|(?:quiet|silent) mode off|stop being (?:quiet|silent)"
                   r"|start talking(?: again)?|(?:thats |that is )?(?:enough )?quiet(?: now)?(?: thank you)?\s*(?:you can talk))"
                   r"(?:\s+(?:please|now|again|thanks|thank you))*$")


def minutes_from(match, default):
    unit = (match.group("unit") or "").lower()
    if unit in ("bit", "while", "moment", "second", "seconds") or not unit:
        return default
    raw = (match.group("n") or "1").lower()
    count = int(raw) if raw.isdigit() else NUMBERS.get(raw, 1)
    if unit.startswith("hour"):
        count *= 60
    return max(1, min(MAX_MINUTES, count))


class QuietVoice:
    def __init__(self, settings, speech_provider, narrator=None):
        self.settings = settings
        self.speech_provider = speech_provider
        self.narrator = narrator

    def _say(self, key, fields=None):
        if self.narrator is not None:
            try:
                self.narrator.say(key, fields or {})
            except Exception:
                log.exception("The quiet voice line failed")

    def try_handle(self, text):
        said = re.sub(r"[^a-z0-9 ]", "", str(text or "").lower().replace("'", "").replace("’", ""))
        said = re.sub(r"\s+", " ", said).strip()
        if not said or len(said) > 70:
            return None
        speech = self.speech_provider()
        if speech is None or not hasattr(speech, "be_quiet"):
            return None
        found = _QUIET.match(said)
        if found:
            minutes = minutes_from(found, int(self.settings.get("speech.quiet_minutes", DEFAULT_MINUTES) or DEFAULT_MINUTES))
            speech.be_quiet(0)                       # stop her mid-sentence first...
            self._say("Quiet_Rude" if _RUDE.search(said) else ("Quiet_Polite" if "please" in said else "Quiet_Ok"), {"minutes": minutes})
            speech.be_quiet(minutes * 60)            # ...then the acknowledgement is allowed (replies to you are), and the chatter waits
            log.info("Quiet for %d minutes (you said %r)", minutes, said)
            return "Quiet for %d minutes." % minutes
        if speech.is_quiet() and _BACK.match(said):
            speech.be_quiet(0)
            self._say("Quiet_Back")
            return "Talking again."
        return None
