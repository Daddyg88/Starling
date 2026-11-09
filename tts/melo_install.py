"""Installs the Australian voice (MeloTTS) into its OWN private folder, data/melo_env, so it can never break Starling.

It makes a separate Python environment there (the same steps the tester's try-out used, which worked), installs MeloTTS without its
old version pins, and writes installed.txt when everything worked. Deleting the folder data/melo_env removes the voice completely.
Needs the internet and several GB of space; it can take 10-20 minutes. install() returns (ok, sentence for the screen).
"""
import subprocess
import sys

from core import paths
from core.logger import get_logger

log = get_logger("melo_install")

MELO_ZIP = "https://github.com/myshell-ai/MeloTTS/archive/refs/heads/main.zip"
ADDONS = ["txtsplit", "cached_path", "transformers", "num2words", "unidic_lite", "unidic", "mecab-python3", "pykakasi", "fugashi",
          "g2p_en", "anyascii", "jamo", "gruut[de,es,fr]", "g2pkk", "librosa", "pydub", "eng_to_ipa", "inflect", "unidecode",
          "pypinyin", "cn2an", "jieba", "langid", "tqdm", "loguru", "numpy", "scipy", "soundfile", "nltk", "huggingface-hub"]
BINARY_ONLY = "fugashi,tokenizers,mecab-python3,safetensors,numpy,scipy,numba,llvmlite,scikit-learn,python-crfsuite,regex"
MARKER = "installed.txt"


def env_dir():
    return paths.DATA_DIR / "melo_env"


def env_python():
    folder = env_dir()
    for candidate in (folder / "Scripts" / "python.exe", folder / "bin" / "python"):
        if candidate.exists():
            return candidate
    return None


def is_installed():
    """True when the private folder was fully installed (installed.txt is written last)."""
    return (env_dir() / MARKER).exists() and env_python() is not None


def uninstall():
    import shutil
    shutil.rmtree(env_dir(), ignore_errors=True)


def steps(python):
    """The commands, as (what to tell the person, command list)."""
    py = str(python)
    return [
        ("Step 1 of 5: installing the sound maths library (torch). This is the big download.",
         [py, "-m", "pip", "install", "--upgrade", "pip", "torch", "torchaudio"]),
        ("Step 2 of 5: installing MeloTTS itself (without its old version pins)...",
         [py, "-m", "pip", "install", "--no-deps", MELO_ZIP]),
        ("Step 3 of 5: installing the add-ons it needs...",
         [py, "-m", "pip", "install", "--only-binary", BINARY_ONLY, "tokenizers", "safetensors", "scikit-learn", "numba"] + ADDONS),
        ("Step 4 of 5: language data (can take a few minutes)...",
         [py, "-m", "unidic", "download"]),
        ("Step 5 of 5: loading the voice once to check it (downloads the voice model, about 200 MB)...",
         [py, "-c", "from melo.api import TTS; m = TTS(language='EN', device='cpu'); assert 'EN-AU' in dict(m.hps.data.spk2id)"]),
    ]


def install(progress=print, run=None, python_for_venv=None):
    """Returns (ok, message). 'run' is replaceable for tests: run(command, log_file) -> exit code."""
    folder = env_dir()
    log_file = folder / "install_log.txt"
    run = run or _run
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if env_python() is None:
            progress("Making the private folder for the Australian voice...")
            if run([str(python_for_venv or sys.executable), "-m", "venv", str(folder)], log_file) != 0:
                return False, "I could not make the private folder (see data/melo_env/install_log.txt)."
        python = env_python()
        if python is None:
            return False, "The private folder was made but has no Python inside it."
        for text, command in steps(python):
            progress(text)
            code = run(command, log_file)
            if code != 0:
                log.warning("Australian voice install: %r exited with %s", command[:4], code)
                return False, ("The Australian voice install stopped at: %s It is safe to try again, nothing in Starling was changed. "
                               "Details are in data/melo_env/install_log.txt." % text.split(":", 1)[0])
        (folder / MARKER).write_text("ok\n", encoding="utf-8")
        return True, "The Australian voice is installed. Choose it in Settings > Voice (the first line she says takes about a minute)."
    except Exception as error:
        log.exception("Australian voice install failed")
        return False, "The Australian voice install failed: %s" % error


def _run(command, log_file):
    with open(log_file, "ab") as handle:
        handle.write(("\n$ " + " ".join(command[:6]) + "\n").encode("utf-8", "replace"))
        handle.flush()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, creationflags=flags).returncode
