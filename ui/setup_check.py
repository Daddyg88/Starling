"""The "Get started" page: a short checklist of what is ready, what is not, and what to do about it, in plain words.

No window code here, so it can be tested. Each item is a dict:
  id, title, state ('ok' | 'wait' | 'todo' | 'bad' | 'optional'), text, action (None or (button words, action id)).
The dashboard (ui/dashboard.py `_build_setup`) draws them and runs the actions.
"""
from core.identity import wake_phrase

OK, WAIT, TODO, BAD, OPTIONAL = "ok", "wait", "todo", "bad", "optional"
SMALLEST_MODEL = "tiny.en"
BETTER_MODEL = "base.en"


def _item(item_id, title, state, text, action=None):
    return {"id": item_id, "title": title, "state": state, "text": text, "action": action}


def _status_rows(app):
    try:
        from ui.status import collect_status
        return {label: (text, tone) for label, text, tone in collect_status(app)}
    except Exception:
        return {}


def game_item(app, finder=None):
    folder = getattr(app, "journal_folder", None)
    if not folder:
        try:
            if finder is None:
                from journal.locator import find_journal_folder as finder
            folder = finder(app.settings.get("journal.folder", ""))
        except Exception:
            folder = None
    if not folder:
        return _item("game", "Elite Dangerous", TODO,
                     "I can't find Elite's journal folder yet. Start Elite Dangerous once and reach the main menu, then press "
                     "Check again. If Elite lives somewhere unusual, type the folder on the Game page.",
                     ("Open the Game page", "page:game"))
    state = getattr(app, "state", None)
    commander = getattr(state, "commander", None) if state is not None else None
    if commander:
        return _item("game", "Elite Dangerous", OK, "Found, and I can see Commander %s." % commander)
    return _item("game", "Elite Dangerous", OK, "Found Elite's journal folder. Start the game and I'll follow along.")


def voice_item(app):
    text, tone = _status_rows(app).get("Voice", ("Not started", "muted"))
    if tone == "good":
        return _item("voice", "Her voice", OK, "Ready. Press the button to hear her.", ("Say hello", "test_voice"))
    if tone == "warn":
        return _item("voice", "Her voice", WAIT, "Still loading. The first start takes a minute or two. This ticks by itself.")
    if tone == "bad":
        return _item("voice", "Her voice", BAD, "She has a problem: %s Open the Developer page and copy the log to send to Claude." % text)
    return _item("voice", "Her voice", TODO, "Her voice is switched off. Turn on 'She speaks aloud' on the Voice page and restart Starling.",
                 ("Open the Voice page", "page:voice"))


def listening_item(app):
    settings = app.settings
    if not settings.get("stt.enabled", False):
        return _item("listening", "Listening to you", TODO,
                     "She isn't listening for your voice yet. Press the button, then close and reopen Starling once.",
                     ("Turn listening on", "listen_on"))
    text, tone = _status_rows(app).get("Listening", ("Starting...", "warn"))
    if tone == "good":
        return _item("listening", "Listening to you", OK,
                     "On. Say \"%s\" and then what you want. If she mishears you, pick your microphone on the Listening page." % wake_phrase(settings),
                     ("Open the Listening page", "page:listening"))
    if tone == "bad":
        return _item("listening", "Listening to you", BAD,
                     "She can't listen: %s Check that a microphone is plugged in and allowed in Windows privacy settings." % text,
                     ("Open the Listening page", "page:listening"))
    return _item("listening", "Listening to you", WAIT, "Starting up. The first time she downloads her ears, so this can take a minute.")


def quality_item(app):
    model = str(app.settings.get("stt.model", BETTER_MODEL) or BETTER_MODEL)
    if model == SMALLEST_MODEL:
        return _item("quality", "How well she hears you", OPTIONAL,
                     "She is using the smallest listening model, which mishears more. 'Balanced' understands you much better and "
                     "is still light on your PC. It downloads once (about 140 MB) and needs a restart.",
                     ("Use Balanced (recommended)", "listen_balanced"))
    return _item("quality", "How well she hears you", OK, "Listening quality is set to %s." % model)


def training_item(app):
    if not app.settings.get("stt.enabled", False):
        return None
    return _item("training", "Teach her your voice", OPTIONAL,
                 "She asks you to say about two dozen short phrases, one at a time (no need to say her name), and learns how you "
                 "sound. Very good if you have a strong accent or she mishears you. Takes about three minutes. You can also say "
                 "\"%s, teach me your voice\" any time." % "Starling",
                 ("Teach her my voice", "train_voice"))


def keys_item(app, summary=None):
    """summary is None until the player has pressed the check: (commands with a key, keys still missing, key clashes)."""
    if summary is None:
        return _item("keys", "Your Elite keys", TODO,
                     "She presses your own keys for voice commands (landing gear, launch, and so on), so each needs a KEYBOARD key in "
                     "Elite: Options > Controls. This checks which ones are missing. She never changes your keys.",
                     ("Check my Elite keys", "check_keys"))
    working, missing, clashes = summary
    if working == 0:
        return _item("keys", "Your Elite keys", BAD,
                     "I couldn't read any keyboard keys. Open Elite once, make sure your controls are saved (press APPLY), then check again.",
                     ("Check my Elite keys", "check_keys"))
    parts = ["%d commands have a keyboard key." % working]
    if missing:
        parts.append("%d still have none (mostly joystick-only buttons). Voice commands for those won't work until you give them a keyboard key." % missing)
    if clashes:
        parts.append("%d keys are shared by two actions, which can make Elite do the wrong thing." % clashes)
    parts.append("The full list is on the Keybinds page.")
    state = OK if not (missing or clashes) else OPTIONAL
    return _item("keys", "Your Elite keys", state, " ".join(parts), ("Open the Keybinds page", "page:keybinds"))


def extras_item(app):
    return _item("extras", "Optional extras", OPTIONAL,
                 "'Prepare her voice' makes her answer quicker (it runs in the background). 'Install AI chat' lets her chat freely "
                 "(about 450 MB, optional).", ("Prepare her voice", "prepare_voice"))


def setup_items(app, key_summary=None, finder=None):
    items = [game_item(app, finder), voice_item(app), listening_item(app), quality_item(app), training_item(app),
             keys_item(app, key_summary), extras_item(app)]
    return [i for i in items if i is not None]


def required_ready(items):
    """True when nothing that she needs is still missing (optional things don't count)."""
    return all(i["state"] in (OK, OPTIONAL) for i in items)


def headline(items):
    if required_ready(items):
        return "You're ready, Commander. Anything marked optional can wait."
    todo = sum(1 for i in items if i["state"] in (TODO, BAD))
    waiting = sum(1 for i in items if i["state"] == WAIT)
    if todo:
        return "%d thing%s to do. Work down the list; each one has a button." % (todo, "" if todo == 1 else "s")
    return "Nearly there. %d thing%s still starting up." % (waiting, "" if waiting == 1 else "s")
