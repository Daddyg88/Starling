"""
THE OPTIONAL SMALL AI MODEL - open conversation for people who want more than her ready-made lines. OFF by default.

What it is: a very small language model (about 400 MB, Qwen2.5 0.5B Instruct, Apache 2.0 licence) that runs ON YOUR
COMPUTER through llama-cpp-python. Nothing is sent anywhere. It is used for exactly one job: the free chat in
personality/brain.py, when you just talk to her and none of her exact patterns, topics or profile answers fit.

What it never does: press a key, fly the ship, answer a crisis (those use her fixed, caring lines), or handle anything
that looks like a game command. Its reply is cleaned (no emojis, no stage directions, no web links, no leaked
"I am an AI model", no bad words unless mature speech is on, short) and if anything is wrong or it takes too long she
silently uses her normal chat lines instead. So switching it on can only add to her, never break her.

Cost: about 0.5 to 1 GB of memory while loaded (it unloads itself after 10 idle minutes) and some CPU for a few seconds
per reply, so it is best for people who do not stream demanding games on a weak PC.

Install: the "Install AI chat" button on the Personality page (works in Starling.exe: it downloads llama.cpp's ready-made
llama-server.exe and the model, see personality/llm_server.py). In a source install, run_install_chat_model.bat (the
llama-cpp-python add-on) still works too. If both are there she uses the downloaded engine.
"""
import re
import threading
import time
import unicodedata

from core import paths
from core.logger import get_logger

log = get_logger("llm")

DEFAULT_FILE = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
IDLE_UNLOAD_SECONDS = 600
MAX_REPLY_CHARS = 260
MAX_REPLY_SENTENCES = 2
MIN_REPLY_WORDS = 3
LEAKS = ("as an ai", "language model", "openai", "alibaba", "qwen", "chatgpt", "i am an ai assistant", "i'm an ai assistant",
         "i am a large", "i don't have personal", "i do not have personal", "my training data", "knowledge cutoff", "as a virtual assistant")
UNSAFE = ("suicide", "kill yourself", "kill myself", "self-harm", "self harm", "hurt yourself", "rape", "porn", "nazi", "heroin", "cocaine",
          "overdose")
SWEARS = ("fuck", "shit", "bitch", "cunt", "bastard", "asshole", "dick", "twat", "wanker", "bollocks")
MOOD_STYLE = {
    "Sarcastic": "You are in a sarcastic mood: dry, teasing, never cruel.",
    "Frustrated": "You are frustrated with the Commander right now: short and a little curt, but still helpful.",
    "Upset": "You are upset with the Commander: cold, brief and a little hurt.",
    "Close": "You are very fond of the Commander: warm and affectionate.",
    "Infatuated": "You are very fond of the Commander: warm, affectionate and a little shy.",
    "Friendly": "You are in a friendly mood: warm and cheerful.",
    "Neutral": "You are calm and professional, with a light touch of humour.",
}
SYSTEM = ("You are Starling, the ship's computer AI aboard the Commander's starship in Elite Dangerous. You are witty, warm and a "
          "little cheeky, never cruel. You are speaking aloud, so reply in one or two short sentences (under 40 words) with no lists, "
          "no emojis, no markdown and no stage directions. You are an AI aboard a ship and never pretend to be human. If you do not "
          "know something, say so plainly and never invent facts, news, numbers or prices. You cannot press keys or fly the ship in "
          "this chat. Do not give medical, legal or financial advice: suggest asking a professional. Stay kind. {mood}{context}")


def clean_reply(text, allow_mature=False):
    """Tidy what the model wrote. None means 'do not use it'."""
    text = (text or "").strip()
    if not text:
        return None
    text = re.sub(r"\*[^*\n]{1,60}\*", " ", text)                       # *smiles* and other stage directions
    text = re.sub(r"[#>`_~]+", " ", text)
    text = re.sub(r"^(?:starling|assistant|ai)\s*:\s*", "", text, flags=re.I)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("So", "Cs", "Co", "Cn", "Cc") or ch in " \n")
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    if not text:
        return None
    letters = [ch for ch in text if ch.isalpha()]
    if not letters or sum(1 for ch in letters if ord(ch) < 0x250) / len(letters) < 0.9:      # mostly Latin letters only
        return None
    lowered = text.lower()
    if any(leak in lowered for leak in LEAKS) or any(bad in lowered for bad in UNSAFE):
        return None
    if "http" in lowered or "www." in lowered or ".com" in lowered or len(re.findall(r"\d", text)) >= 8:
        return None
    if not allow_mature and any(word in lowered for word in SWEARS):
        return None
    words = lowered.split()
    if any(words[i] == words[i + 1] == words[i + 2] == words[i + 3] for i in range(len(words) - 3)):
        return None                                                      # stuck in a loop
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text)
    text = "".join(sentences[:MAX_REPLY_SENTENCES]).strip()
    if len(text) > MAX_REPLY_CHARS:
        cut = text[:MAX_REPLY_CHARS]
        end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        text = cut[:end + 1] if end > 40 else None
    if not text or len(text.split()) < MIN_REPLY_WORDS:
        return None
    return text


def build_messages(user_text, mood="", system_name="", ship="", likes=None, history=()):
    """The chat the model sees: who she is, a little context, the last few exchanges, and what was just said."""
    context = []
    if system_name:
        context.append("You are currently in the %s system." % system_name)
    if ship:
        context.append("The ship is a %s." % ship)
    if likes:
        context.append("The Commander has told you they like: %s." % ", ".join(likes[:5]))
    system = SYSTEM.format(mood=MOOD_STYLE.get(mood or "Neutral", MOOD_STYLE["Neutral"]) + " ",
                           context=(" " + " ".join(context)) if context else "")
    messages = [{"role": "system", "content": system}]
    for said, answered in list(history)[-3:]:
        messages.append({"role": "user", "content": said})
        messages.append({"role": "assistant", "content": answered})
    messages.append({"role": "user", "content": user_text})
    return messages


class LocalLLM:
    def __init__(self, settings, loader=None, clock=time.monotonic, engine_finder=None, server_factory=None):
        self.settings = settings
        self._loader = loader                 # tests give a fake; None = the downloaded engine, or llama-cpp-python
        self._engine_finder = engine_finder   # tests: where llama-server.exe is (None = the real data/llm/engine folder)
        self._server_factory = server_factory
        self.clock = clock
        self._model = None
        self._lock = threading.Lock()
        self._busy = False
        self._last_used = 0.0
        self._timer = None
        self._import_ok = None

    # ---- state ----
    def enabled(self):
        return bool(self.settings.get("llm.enabled", False))

    def model_path(self):
        custom = str(self.settings.get("llm.model_file", "") or "").strip()
        from pathlib import Path
        return Path(custom) if custom else paths.DATA_DIR / "models" / DEFAULT_FILE

    def _can_import(self):
        if self._import_ok is None:
            try:
                import llama_cpp  # noqa: F401
                self._import_ok = True
            except Exception:
                self._import_ok = False
        return self._import_ok

    def _engine(self):
        """The downloaded llama-server.exe, or None."""
        from personality import llm_server
        return (self._engine_finder or llm_server.engine_exe)()

    def problem(self):
        """What is missing (a sentence), or '' if the model could be used. Ignores the on/off switch."""
        if self._loader is not None:
            return ""
        if self._engine() is None and not self._can_import():
            return "The AI chat is not installed yet. Press 'Install AI chat' on the Personality page"
        if not self.model_path().is_file():
            return "The model file is missing. Press 'Install AI chat' on the Personality page"
        return ""

    def status(self):
        """A sentence for the dashboard."""
        if not self.enabled():
            return "Off"
        problem = self.problem()
        if problem:
            return "Switched on, but " + problem[0].lower() + problem[1:]
        return "Ready" if self._model is not None else "Ready (loads on first use)"

    def ready(self):
        return self.enabled() and self.status().startswith(("Ready",))

    # ---- model ----
    def _load(self):
        with self._lock:
            if self._model is not None:
                return True
            try:
                threads = max(1, min(8, int(self.settings.get("llm.threads", 2) or 2)))
                engine = None if self._loader is not None else self._engine()
                if self._loader is not None:
                    self._model = self._loader(str(self.model_path()), threads)
                elif engine is not None:
                    from personality import llm_server
                    log.info("Starting the small chat model (%s)...", self.model_path().name)
                    self._model = (self._server_factory or llm_server.ServerModel)(engine, self.model_path(), threads).start()
                else:
                    from llama_cpp import Llama
                    log.info("Loading the small chat model (%s)...", self.model_path().name)
                    self._model = Llama(model_path=str(self.model_path()), n_ctx=1024, n_threads=threads, verbose=False)
                    log.info("Chat model ready.")
                return True
            except Exception:
                log.exception("The chat model could not be loaded; free chat uses her normal lines")
                self._model = None
                return False

    def unload(self):
        with self._lock:
            model, self._model = self._model, None
        close = getattr(model, "close", None)                 # the engine program is stopped, so its memory comes back
        if close is not None:
            try:
                close()
            except Exception:
                log.debug("Closing the chat model failed", exc_info=True)

    def test(self):
        """For the dashboard's test button (works even when the switch is off). Returns (ok, sentence for the screen)."""
        problem = self.problem()
        if problem:
            return False, problem
        started = time.monotonic()
        messages = build_messages("Say hello to me in one short sentence.", "Friendly")
        holder = {}

        def work():
            try:
                if self._load():
                    holder["text"] = self._model.create_chat_completion(messages=messages, max_tokens=60, temperature=0.8)["choices"][0]["message"]["content"]
            except Exception as exc:
                log.exception("The AI chat test failed")
                holder["error"] = str(exc)
        thread = threading.Thread(target=work, name="llm-test", daemon=True)
        thread.start()
        thread.join(60)
        seconds = time.monotonic() - started
        if thread.is_alive():
            return False, "The AI chat took more than a minute. This PC may be too slow for it."
        text = clean_reply(holder.get("text")) or (holder.get("text") or "").strip()
        if not text:
            return False, "The AI chat started but gave no answer. %s" % holder.get("error", "Check the log.")
        self._last_used = self.clock()
        self._schedule_unload()
        return True, "It works (%.1f seconds). She said: %s" % (seconds, text)

    def _schedule_unload(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(IDLE_UNLOAD_SECONDS + 5, self._unload_if_idle)
        self._timer.daemon = True
        self._timer.start()

    def _unload_if_idle(self):
        if not self._busy and self.clock() - self._last_used >= IDLE_UNLOAD_SECONDS:
            self.unload()
            log.info("Chat model unloaded after being idle.")

    # ---- talking ----
    def reply(self, messages, allow_mature=False, max_tokens=70, timeout=None):
        """One cleaned reply, or None (switched off, busy, too slow, broken, or an unusable answer)."""
        if not self.ready() or self._busy:
            return None
        timeout = float(timeout if timeout is not None else self.settings.get("llm.max_seconds", 8) or 8)
        if self._model is None and self._loader is None:
            timeout += 12                                      # the first reply also has to start the engine and load the model
        holder = {}

        def work():
            try:
                if not self._load():
                    return
                done = self._model.create_chat_completion(messages=messages, max_tokens=max_tokens, temperature=0.8, top_p=0.9,
                                                          repeat_penalty=1.15, stop=["\n\n", "User:", "Commander:"])
                holder["text"] = done["choices"][0]["message"]["content"]
            except Exception:
                log.exception("The chat model failed on a reply")
            finally:
                self._busy = False

        self._busy = True
        thread = threading.Thread(target=work, name="llm", daemon=True)
        thread.start()
        thread.join(timeout)
        self._last_used = self.clock()
        if thread.is_alive():
            log.warning("The chat model took longer than %.0f s; using her normal chat lines", timeout)
            return None
        self._schedule_unload()
        return clean_reply(holder.get("text"), allow_mature)
