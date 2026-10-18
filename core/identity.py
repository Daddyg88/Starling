"""
Who she is and who you are - in ONE place.

    her name         settings "app.name"          (default Starling)
    her wake word    settings "stt.wake_phrase"   (empty = same as her name)
    your sex         settings "player.sex"        ("neutral", "male" or "female")

In dialogue files, write @NAME@ wherever she says her own name; it is filled in when she speaks.
"""

DEFAULT_NAME = "Starling"
NAME_TOKEN = "@NAME@"
SEX_CHOICES = ("neutral", "male", "female")
_OLD_NAMES = ("tetko",)      # names from earlier versions that should follow the new name


def assistant_name(settings):
    name = str(settings.get("app.name", DEFAULT_NAME) or "").strip() if settings is not None else ""
    return name or DEFAULT_NAME


def wake_phrase(settings):
    phrase = str(settings.get("stt.wake_phrase", "") or "").strip() if settings is not None else ""
    if not phrase or phrase.lower() in _OLD_NAMES:
        return assistant_name(settings)
    return phrase


def personalise(text, settings):
    """Fill in her name wherever the dialogue says @NAME@."""
    if text and NAME_TOKEN in text:
        return text.replace(NAME_TOKEN, assistant_name(settings))
    return text


def commander_sex(settings):
    sex = str(settings.get("player.sex", "neutral") or "neutral").lower() if settings is not None else "neutral"
    return sex if sex in SEX_CHOICES else "neutral"


def sex_label(settings):
    """The word used to pick gendered lines: 'Male', 'Female' or '' (no preference)."""
    return {"male": "Male", "female": "Female"}.get(commander_sex(settings), "")
