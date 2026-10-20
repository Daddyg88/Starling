"""The list of every voice provider STARLING knows about."""

from pathlib import Path

from tts.azure_tts import AzureTTS
from tts.elevenlabs_tts import ElevenLabsTTS
from tts.kokoro_tts import KokoroTTS
from tts.piper_tts import PiperTTS
from tts.prerecorded_tts import PrerecordedTTS
from tts.windows_tts import WindowsTTS

# Providers that turn TEXT into speech (choose one in settings.json: "tts" > "provider").
TEXT_PROVIDERS = ("kokoro", "windows", "piper", "elevenlabs", "azure")


def recover_pack(pack, previous_root=None):
    """
    After an update the new app folder has no tuned voice file (custom_covas.pt), so she would tune a new one and
    then remake EVERY saved line. The old version is still sitting next to it (app.previous), so copy the file across.
    Returns True when it was recovered.
    """
    import shutil
    from core import paths
    from core.logger import get_logger
    pack = Path(pack)
    try:
        if pack.exists():
            return False
        previous = Path(previous_root) if previous_root else paths.ROOT.with_name(paths.ROOT.name + ".previous")
        old = previous / pack.name
        if old.is_file() and old.stat().st_size > 0:
            shutil.copy2(old, pack)
            get_logger("providers").info("Kept her tuned voice from the previous version (%s)", pack.name)
            return True
    except OSError:
        pass
    return False


def build_providers(settings=None):
    """Returns {"windows": <WindowsTTS>, "recorded": <PrerecordedTTS>, ...}"""
    from core import paths
    pack = paths.ROOT / (settings.get("tts.clone_pack", "custom_covas.pt") if settings else "custom_covas.pt")
    reference = paths.ROOT / (settings.get("tts.clone_reference", "voicepacks/default/clone/Tetko_Issued_Notice.mp3")
                              if settings else "voicepacks/default/clone/Tetko_Issued_Notice.mp3")
    recover_pack(pack)
    providers = {}
    for provider in (KokoroTTS(pack, reference, cache_dir=paths.DATA_DIR / "voice_cache"), WindowsTTS(), PiperTTS(), ElevenLabsTTS(), AzureTTS(), PrerecordedTTS()):
        providers[provider.name] = provider
    return providers
