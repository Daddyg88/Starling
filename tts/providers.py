"""The list of every voice provider STARLING knows about."""

from tts.azure_tts import AzureTTS
from tts.elevenlabs_tts import ElevenLabsTTS
from tts.kokoro_tts import KokoroTTS
from tts.piper_tts import PiperTTS
from tts.prerecorded_tts import PrerecordedTTS
from tts.windows_tts import WindowsTTS

# Providers that turn TEXT into speech (choose one in settings.json: "tts" > "provider").
TEXT_PROVIDERS = ("kokoro", "windows", "piper", "elevenlabs", "azure")


def build_providers(settings=None):
    """Returns {"windows": <WindowsTTS>, "recorded": <PrerecordedTTS>, ...}"""
    from core import paths
    pack = paths.ROOT / (settings.get("tts.clone_pack", "custom_covas.pt") if settings else "custom_covas.pt")
    reference = paths.ROOT / (settings.get("tts.clone_reference", "voicepacks/default/clone/Tetko_Issued_Notice.mp3")
                              if settings else "voicepacks/default/clone/Tetko_Issued_Notice.mp3")
    providers = {}
    for provider in (KokoroTTS(pack, reference, cache_dir=paths.DATA_DIR / "voice_cache"), WindowsTTS(), PiperTTS(), ElevenLabsTTS(), AzureTTS(), PrerecordedTTS()):
        providers[provider.name] = provider
    return providers
