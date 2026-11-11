"""Builds the chat bridge out of the running app (the only streaming file that knows about the rest of Starling)."""

import time

from core.logger import get_logger
from streaming.bridge import ChatBridge
from streaming.chat import FSD_CHARGING, FSD_JUMP, IN_DANGER, ChatDirector, flag

log = get_logger("streaming")
QUIET_SECONDS = 4.0          # she must have been silent this long before a held chat question is answered


def make_chat_brain(app):
    """A second, smaller brain for chat. It can answer questions but it can NOT learn anything: no profile, no friends list,
    no 'unanswered questions' list and no follow-up prompts, so a viewer can never change what she knows about you."""
    from personality.brain import Brain
    from personality.ships_info import ShipInfo
    main = app.brain
    brain = Brain(app.speech, app.dialogue, app.settings, state_provider=lambda: app.state, chitchat=app.chitchat,
                  facts=getattr(app.ask, "facts", None), mining=app.miner, prices=app.prices, ask=None, merit=app.merit,
                  services=app.services, stats=app.stats, profile=None, llm=app.llm, lookup=app.lookup, unanswered=None,
                  people=None, ships=ShipInfo(), intents=main.intents, meaning=main.meaning, knowledge=main.knowledge)
    brain.topics = main.topics
    return brain


def asks_key(times, settings):
    """Which announcement to use: a first question gets the normal one; a viewer who has asked before gets a 'welcome back' one,
    and a regular (three or more) a friendlier one. Off with streaming.recognise_viewers."""
    if not settings.get("streaming.recognise_viewers", True):
        return "StreamChat_Asks"
    if times >= 2:
        return "StreamChat_Asks_Regular"
    if times == 1:
        return "StreamChat_Asks_Again"
    return "StreamChat_Asks"


def build(app):
    """The chat bridge for this app, or None if something it needs is missing."""
    from navigation.voice import Narrator
    narrator = Narrator(lambda: app.speech, lambda: app.dialogue, app.settings)
    holder = {}

    def say(key, fields=None):
        return narrator.say(key, fields)

    def do_action(action):
        runner = app.ensure_commands()
        if runner is None:
            return False
        outcomes = runner.run_text(action.phrase, speak_unknown=False)
        return bool(outcomes) and outcomes[0].status == "done"

    def do_ask(user, question):
        if app.brain is None:
            return False
        if "brain" not in holder:
            holder["brain"] = make_chat_brain(app)
        times = director.asked.get(user, 0)
        if app.settings.get("streaming.announce", True):
            say(asks_key(times, app.settings), {"user": user, "question": question[:90], "times": times + 1})
        reply = holder["brain"].try_handle(question, deliberate=True)
        if reply is None:
            say("StreamChat_NoAnswer", {"user": user})
            return False
        director.asked[user] = times + 1
        return True

    def quiet():
        """True when a chat question can be answered without talking over anything: she is not speaking, has been silent a few
        seconds, and the game is calm (no fight, no danger, no jump or charging)."""
        speech = app.speech
        if speech is not None and speech.is_busy():
            return False
        chit = getattr(app, "chitchat", None)
        if chit is not None:
            if getattr(chit, "mode", "") == "combat":
                return False
            if time.monotonic() - getattr(chit, "last_spoke", -1e9) < QUIET_SECONDS:
                return False
        state = app.state
        if state is not None and any(flag(state, bit) for bit in (IN_DANGER, FSD_JUMP, FSD_CHARGING)):
            return False
        return True

    director = ChatDirector(app.settings, lambda: app.state, do_action, do_ask, say, time.monotonic, quiet_provider=quiet)
    return ChatBridge(app.settings, director)
