"""One place that decides how much of the graphics card Starling may use (setting gpu.limit_percent, default 70).

A program cannot make Windows hold the graphics card at an exact "70 percent busy" for another program, so the limit is kept the only
ways that really work:
  * AI chat (llama-server): only that share of the model's layers go on the card (70% of them); the rest run on the processor. That
    takes the same share of the card's memory and of its work, so the game keeps room.
  * Her voice (torch): the card memory her voice may take is capped to that share of the card (torch.cuda.set_per_process_memory_fraction).
100 means no limit. Applied when Starling starts (restart after changing it)."""

import struct
from pathlib import Path

from core.logger import get_logger

log = get_logger("gpulimit")

DEFAULT_LAYERS = 32           # used when the model file's layer count cannot be read (a normal 7B model has 32)
_percent = 100                # until the app reads settings.json (so a plain test or tool run is unchanged)


def set_percent(value):
    global _percent
    try:
        _percent = max(10, min(100, int(value)))
    except (TypeError, ValueError):
        _percent = 100


def percent():
    return _percent


# ---------------------------------------------------------------- how many layers does the model have?
_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}       # GGUF value types with a fixed size in bytes


def _skip(f, kind):
    if kind in _SIZES:
        f.seek(_SIZES[kind], 1)
    elif kind == 8:                                            # string
        f.seek(struct.unpack("<Q", f.read(8))[0], 1)
    elif kind == 9:                                            # array
        inner, count = struct.unpack("<IQ", f.read(12))
        for _ in range(count):
            _skip(f, inner)
    else:
        raise ValueError("unknown GGUF value type %d" % kind)


def model_layers(path):
    """The number of layers (<arch>.block_count) written in a .gguf model's header, or 0 if it cannot be read."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"GGUF":
                return 0
            version, _tensors, count = struct.unpack("<IQQ", f.read(20))
            if version < 2:
                return 0
            for _ in range(count):
                key = f.read(struct.unpack("<Q", f.read(8))[0]).decode("utf-8", "replace")
                kind = struct.unpack("<I", f.read(4))[0]
                if key.endswith(".block_count") and kind in (4, 5, 10, 11):
                    return int(struct.unpack("<I" if kind in (4, 5) else "<Q", f.read(4 if kind in (4, 5) else 8))[0])
                _skip(f, kind)
    except (OSError, ValueError, struct.error):
        pass
    return 0


def gpu_layers(model_path=None, percent_now=None):
    """The value for llama-server's -ngl: 99 (everything) with no limit, else that share of the model's layers (at least 1)."""
    pct = _percent if percent_now is None else max(10, min(100, int(percent_now)))
    if pct >= 100:
        return 99
    layers = model_layers(model_path) if model_path else 0
    return max(1, int(round((layers or DEFAULT_LAYERS) * pct / 100.0)))


# ---------------------------------------------------------------- her voice (torch)
def cap_torch_memory(torch_module, percent_now=None):
    """Caps how much card memory this program's torch may take. Returns a sentence for the log, or '' if nothing was done."""
    pct = _percent if percent_now is None else percent_now
    if pct >= 100:
        return ""
    try:
        if not torch_module.cuda.is_available():
            return ""
        torch_module.cuda.set_per_process_memory_fraction(pct / 100.0, 0)
        return "Her voice may use at most %d%% of the graphics card's memory (setting gpu.limit_percent)." % pct
    except Exception as error:                                  # a cap that cannot be set must never stop her voice
        return "Could not cap the graphics card memory for her voice (%s)" % error
