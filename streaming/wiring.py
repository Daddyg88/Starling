"""Builds the chat bridge out of the running app (the only streaming file that knows about the rest of Starling)."""

import time

from core.logger import get_logger
from streaming.bridge import ChatBridge
from streaming.chat import spoken_name, FSD_CHARGING, FSD_JUMP, IN_DANGER, ChatDirector, flag

log = get_logger("streaming")
FREE_SECONDS = 1.5           # a thank-you or o7 waits only this long after she last spoke (fights do not matter)
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


def make_intro(app, narrator, free):
    """The 'ten minute intro' (streaming/intro.py) tied to her voice, the local AI model and the hologram."""
    from core.identity import personalise
    from streaming.intro import StreamIntro

    def say_text(text):
        speech = app.speech
        if speech is None or not app.settings.get("speech.enabled", True):
            return False
        return bool(speech.say(text=personalise(text, app.settings), priority="normal", event_name="personality.intro"))

    def ask_llm(messages):
        llm = getattr(app, "llm", None)
        if llm is None:
            return None
        return llm.reply(messages, allow_mature=bool(app.settings.get("speech.allow_mature", False)), max_tokens=60)

    def publish(name):
        bus = getattr(app, "bus", None)
        if bus is not None:
            bus.publish(name)

    return StreamIntro(app.settings, narrator.say, say_text, ask_llm, free, publish)


def show_comment(app, user, text, bridge=None):
    """Puts the comment she is about to answer on the screen (it goes by itself once she has finished speaking). Never raises."""
    try:
        pin = getattr(app, "chat_pin", None)
        if pin is None or not app.settings.get("streaming.pin_overlay", True) or not app.settings.get("streaming.pin_replies", True):
            return
        platform, full = "", text
        feed = getattr(bridge, "feed", None) if bridge is not None else None
        if feed is not None:
            for line in reversed(feed.since(0)):
                if line.kind == "chat" and line.user == user and str(text or "")[:20].lower() in line.text.lower():
                    platform, full = line.platform, line.text
                    break
        pin.show_for_reply(user, full, platform)
    except Exception:
        log.exception("Could not show the chat comment on the screen")


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

    def do_ask(user, question, chime=False):
        if app.brain is None:
            return False
        if "brain" not in holder:
            holder["brain"] = make_chat_brain(app)
        times = director.asked.get(user, 0)
        show_comment(app, user, question, holder.get("bridge"))
        if app.settings.get("streaming.announce", True):
            say("StreamChat_Chime" if chime else asks_key(times, app.settings), {"user": spoken_name(user), "question": question[:90], "times": times + 1})
        reply = holder["brain"].try_handle(question, deliberate=True)
        if reply is None:
            say("StreamChat_NoAnswer", {"user": spoken_name(user)})
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

    def free():
        """Lenient check for thank-yous, o7 and a viewer's own question: only 'is she speaking, or did she just finish'. A fight or danger does
        not hold these back, or a streamer who fights all night never gets a raid answered."""
        speech = app.speech
        if speech is not None and speech.is_busy():
            return False
        chit = getattr(app, "chitchat", None)
        if chit is not None and time.monotonic() - getattr(chit, "last_spoke", -1e9) < FREE_SECONDS:
            return False
        return True

    director = ChatDirector(app.settings, lambda: app.state, do_action, do_ask, say, time.monotonic, quiet_provider=quiet, free_provider=free)
    bridge = ChatBridge(app.settings, director)
    holder["bridge"] = bridge
    bridge.intro = make_intro(app, narrator, free)
    bridge.intro.pin = lambda user, text: show_comment(app, user, text, bridge)
    app.stream_intro = bridge.intro
    return bridge
