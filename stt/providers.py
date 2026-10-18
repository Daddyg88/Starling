"""The list of every listening provider STARLING knows about."""

from stt.faster_whisper_stt import FasterWhisperSTT
from stt.whisper_stt import WhisperSTT
from stt.windows_stt import WindowsSTT


def build_stt_providers(settings=None):
    size = settings.get("stt.model", "tiny.en") if settings else "tiny.en"
    providers = {}
    for provider in (FasterWhisperSTT(size), WhisperSTT(), WindowsSTT()):
        providers[provider.name] = provider
    return providers


def choose_stt(providers, settings):
    """The provider named in settings.json, or Faster-Whisper if that one is not built yet."""
    wanted = settings.get("stt.provider", "faster_whisper")
    for name in (wanted, "faster_whisper"):
        provider = providers.get(name)
        if provider is not None and provider.available()[0]:
            return provider
    return None
