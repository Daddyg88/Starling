"""
SMALL TALK - things you can simply say to her, and she answers like a companion rather than a command line.

  "Starling, how are you?"          "Starling, tell me a joke"       "Starling, talk to me"
  "Starling, I'm bored"             "Starling, good job"             "Starling, are you there?"
  "Starling, good morning"          "Starling, good night"           "Starling, what's your name?"
  "Starling, what are you?"  "tell me about yourself"  "who made you?"  "tell me more"   (her back story: see lore.py)

Only a WHOLE sentence like these counts, so a real command is never mistaken for chat.
Her answers live in voicepacks/default/smalltalk.json (keys Talk_*), one pool per mood.
Kind words ("good job") give her a small mood lift; nothing here can ever lower it.
"""
import re

from core.event_bus import Event
from core.identity import assistant_name, personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("smalltalk")

_FILL = r"(?:\s+(?:please|starling|commander|then|today|there|now))*"

# (key, regex). The text is lower case with punctuation removed.
INTENTS = [
    ("Talk_HowAreYou", r"(?:how are you(?: doing| feeling| today| holding up)?|how(?: is|s) it going|are you (?:ok|okay|alright|all right|well|good)|you (?:ok|okay|alright)|how do you feel)"),
    ("Talk_Joke", r"(?:tell me a joke|got any jokes|do you know any jokes|make me laugh|say something funny|tell a joke|joke)"),
    ("Talk_Chat", r"(?:talk to me|chat to me|chat with me|say something|keep me company|tell me something|i(?: am|m) bored|im bored|entertain me|speak to me)"),
    ("Talk_Here", r"(?:are you (?:there|listening|awake|still there|with me)|you there|can you hear me)"),
    ("Talk_Hello", r"(?:hello|hi|hey|hiya|howdy|good (?:morning|afternoon|evening)|morning|evening)"),
    ("Talk_Goodnight", r"(?:good night|goodnight|night night|i(?: am|m) (?:going to bed|off to bed|off|done for (?:the night|today)|signing off|logging off)|i have to go|i(?: am|m) heading off)"),
    ("Talk_Back", r"(?:i(?: am|m) back|im back|i(?: have|ve) returned)"),
    ("Talk_Compliment", r"(?:good (?:job|girl|work)|well done|nice (?:one|work|job)|great (?:job|work)|you(?: are|re) (?:amazing|brilliant|the best|great|wonderful|awesome|clever|good)|you(?: are|re) doing (?:great|well|brilliantly)|i like you|i appreciate you|i(?: am|m) glad you(?: are|re) here)"),
    ("Talk_Love", r"(?:i love you|love you|i adore you)"),
    ("Talk_FavouriteShip", r"(?:what(?: is|s) your favou?rite ship|which(?: ship)? (?:is|do you like|do you love) (?:your favou?rite|best)|which ship do you (?:like|love|prefer)(?: the most| best)?|do you have a favou?rite ship|favou?rite ship)"),
    ("Talk_Thinking", r"(?:what are you (?:thinking|up to|doing)|penny for your thoughts|what(?: is|s) on your mind)"),
    ("Talk_Name", r"(?:what(?: is|s) your name|who are you|what are you called|introduce yourself|what should i call you)"),
    ("Talk_What", r"(?:what are you|what kind of (?:ai|thing|computer|machine) are you|what exactly are you|are you (?:a |an )?(?:robot|ai|human|real|person|computer|machine|program|bot|intelligence))"),
    ("Talk_Story", r"(?:tell me (?:about yourself|about you|your story|your back ?story|your history|about your past|more about yourself)|where do you come from|where are you from|who (?:made|built|created|designed|programmed) you|what(?: is|s) your (?:story|back ?story|history)|what happened to you|"
                   r"(?:tell me )?(?:about|what is|what was|who (?:is|was|were)) the east orion company|east orion company|where were you made)"),
    ("Talk_More", r"(?:tell me more|go on|carry on|and then|what happened next|what happened then|then what|continue|more)"),
]
LORE_KEYS = ("Talk_Name", "Talk_What", "Talk_Story", "Talk_More")
_COMPILED = [(key, re.compile(r"^" + body + _FILL + r"$")) for key, body in INTENTS]
KIND = ("Talk_Compliment", "Talk_Love", "Talk_Back")


def clean(text):
    text = re.sub(r"['’]", "", (text or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def intent_for(text):
    """The Talk_* key for a whole sentence of small talk, or None."""
    tidy = clean(text)
    if not tidy:
        return None
    tidy = re.sub(r"^(?:hey |hi |ok |okay )?(?:starling )", "", tidy) or tidy
    for key, pattern in _COMPILED:
        if pattern.match(tidy):
            return key
    return None


class SmallTalk:
    def __init__(self, speech, dialogue, settings, chitchat=None, mood=None, lore=None, eoc=None, favourite=None):
        self.favourite = favourite       # personality/favourite_ship.py
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.chitchat = chitchat
        self.mood = mood
        self.lore = lore                 # personality/lore.py: her back story
        self.eoc = eoc                   # personality/eoc.py: the East Orion Company, its CEO and systems

    def try_handle(self, text):
        """Answer small talk. Returns what she said, or None if this wasn't small talk."""
        key = intent_for(text)
        if key is None or self.dialogue is None or not self.settings.get("smalltalk.enabled", True):
            if (self.eoc is not None and self.dialogue is not None and self.settings.get("smalltalk.enabled", True)):
                return self.eoc.try_handle(text)          # questions about the company that are not small talk
            return None
        if self.eoc is not None:
            if key == "Talk_More" and self.eoc.recent():
                told = self.eoc.next()                    # "tell me more" after a company answer = next system
                if told:
                    return told
            told = self.eoc.try_handle(text)              # before her back story: the company has its own answers
            if told:
                return told
        if key in LORE_KEYS and self.lore is not None:
            if key == "Talk_More" and not self.lore.recent():
                return None                                  # "more" on its own means nothing unless she was just telling a story
            told = self.lore.tell()
            if told:
                return told                                  # the lore teller speaks by itself
            if key == "Talk_More":
                return None
        if key == "Talk_More":
            return None
        if key == "Talk_FavouriteShip":
            return self._favourite_answer()
        if key == "Talk_Chat" and self.chitchat is not None:
            said = self.chitchat.say_now()                 # speaks by itself
            if said:
                return said
        mood = effective_mood(self.settings) if self.settings.get("personality.style", "personality") == "personality" else ""
        line = self.dialogue.pick(key, mood or "", bool(self.settings.get("speech.allow_mature", False)), False)
        if line is None:
            return None
        reply = personalise(line.text.replace("{name}", assistant_name(self.settings)), self.settings)
        if self.speech is not None and self.settings.get("speech.enabled", True):
            self.speech.say(text=reply, priority="normal", event_name="smalltalk")
        if key in KIND and self.mood is not None:
            try:
                self.mood.on_event(Event(name="Complimented", data={}, priority="normal"))
            except Exception:
                log.exception("Could not record the kind word")
        return reply

    def _favourite_answer(self):
        """'What is your favourite ship?' She names it, or says how far along she is."""
        mood = effective_mood(self.settings) if self.settings.get("personality.style", "personality") == "personality" else ""
        label = self.favourite.favourite_label() if self.favourite is not None else None
        key = "Talk_FavouriteShip" if label else "Talk_FavouriteShip_None"
        line = self.dialogue.pick(key, mood or "", bool(self.settings.get("speech.allow_mature", False)), False)
        if line is None:
            return None
        reply = personalise(line.text.replace("{ship}", label or ""), self.settings)
        if self.speech is not None and self.settings.get("speech.enabled", True):
            self.speech.say(text=reply, priority="normal", event_name="smalltalk")
        return reply
