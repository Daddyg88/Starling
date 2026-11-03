"""Builds the chat bridge out of the running app (the only streaming file that knows about the rest of Starling)."""

import time

from core.logger import get_logger
from streaming.bridge import ChatBridge
from streaming.chat import ChatDirector

log = get_logger("streaming")


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


def build(app):
    """The chat bridge for this app, or None if something it needs is missing."""
    from navigation.voice import Narrator
    narrator = Narrator(lambda: app.speech, lambda: app.dialogue, app.settings)
    holder = {}

    def say(key, fields=None):
        narrator.say(key, fields)

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
        if app.settings.get("streaming.announce", True):
            say("StreamChat_Asks", {"user": user, "question": question[:90]})
        reply = holder["brain"].try_handle(question, deliberate=True)
        if reply is None:
            say("StreamChat_NoAnswer", {"user": user})
            return False
        return True

    director = ChatDirector(app.settings, lambda: app.state, do_action, do_ask, say, time.monotonic)
    return ChatBridge(app.settings, director)
