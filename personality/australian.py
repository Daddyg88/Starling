"""AUSTRALIAN MODE: when, and only when, she is using the Australian voice (Voice page: Australian, MeloTTS), she also talks a little Australian.

What changes (and only then):
  - now and then a short Australian word before or after an ordinary line ("Righto." / "No worries.")   (Flavour.apply)
  - some pet names are Australian ("Mate", "Legend", "Champ")                                           (Flavour._pet_name)
  - some of her little remarks are Australian, with Melbourne and Victoria in them                      (Flavour._remark)
  - every so often she shares a bit of Australian slang or Melbourne life when it is quiet              (ChitChat pool ChitChat_Aussie)
The lines are in voicepacks/default/aussie.json. Nothing here touches warnings, red alert or a fight, and the switch
Personality > "Australian slang with the Australian voice" turns it all off.
"""

AUSTRALIAN_VOICE = "melo_en_au"


def australian_on(settings):
    """True only while the Australian voice is chosen, the switch is on and she is in 'personality' style (not 'info only')."""
    try:
        return (str(settings.get("tts.voice", "")) == AUSTRALIAN_VOICE
                and bool(settings.get("personality.aussie_slang", True))
                and settings.get("personality.style", "personality") == "personality")
    except Exception:
        return False
