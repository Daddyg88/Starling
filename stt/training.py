"""
VOICE TRAINING - "Starling, teach me your voice".

She asks you to say about two dozen key phrases, one at a time, no wake word needed. For each one she compares what the
microphone heard with what she asked for:
  * the same        -> fine, nothing to do.
  * close but wrong -> that is YOUR accent or mic being mis-heard. She learns it at once (control/learning.py) so the
                       same slip is understood exactly from now on.
  * nowhere near    -> counted as unclear (not learned, so a cough never becomes a command).
Only the big, safe phrases are used (never jumping or other strict commands), and only mishearings of those are learned.

"Starling, hearing report" (or the end of the session) writes data/hearing_report.txt: what she heard against what was
meant, your listening quality setting and the totals. It contains NO game data and is plain text, so you can send it to
whoever is tuning her for you. The model never leaves your PC unless you send the file yourself.
"""
import difflib
import json
import re
import time
from datetime import datetime

from control.matcher import normalise
from core import paths
from core.logger import get_logger

log = get_logger("training")

START = re.compile(r"\b(teach (?:me|you) (?:to )?(?:understand )?(?:my|your) voice|teach her my voice|(?:voice|speech) (?:training|lesson|teaching)|"
                   r"train (?:to )?(?:my|your) voice|learn my voice|learn my accent|(?:do|run|start) (?:a |the )?(?:hearing|listening) test)\b")
REPORT = re.compile(r"\b(hearing|listening) report\b|\breport (?:on )?(?:your |what you )?hearing\b")
CANCEL = {"stop", "cancel", "quit", "enough", "stop training", "never mind", "nevermind", "that is enough", "exit"}
SKIP = {"skip", "next", "pass", "skip it"}
SESSION_SECONDS = 600
CLOSE_ENOUGH = 0.45
MAX_REPORT_ROWS = 200


def load_phrases():
    try:
        with open(paths.CONFIG_DIR / "training_phrases.json", "r", encoding="utf-8") as handle:
            return [str(p) for p in json.load(handle).get("phrases", [])]
    except Exception:
        log.exception("Could not load the voice training phrases")
        return []


def strip_name(text):
    return re.sub(r"^(?:hey |ok |okay )?starling[ ,]+", "", (text or "").strip(), flags=re.I)


class VoiceTrainer:
    def __init__(self, phrases, learning, say, settings, report_path=None, clock=time.monotonic):
        self.phrases = list(phrases)
        self.learning = learning
        self.say = say                       # say(key, fields, fallback)
        self.settings = settings
        self.report_path = report_path or (paths.DATA_DIR / "hearing_report.txt")
        self.clock = clock
        self.index = -1
        self.rows = []                       # [(expected, heard, result)] of this session; result: ok / learned / unclear / skipped
        self.history = []                    # rows of earlier sessions this run (the report shows them all)
        self.until = 0.0

    # ---- state ----
    def active(self):
        return self.index >= 0

    # ---- addressed helper (via the runner's helper list) ----
    def try_handle(self, text):
        clean = (text or "").lower().replace("'", "")
        if REPORT.search(clean):
            where = self.write_report()
            self.say("Training_Report", {"where": where}, "Hearing report saved: %s" % where)
            return "report"
        if START.search(clean):
            if not self.phrases:
                return None
            self.rows, self.index = [], 0
            self.until = self.clock() + SESSION_SECONDS
            self.say("Training_Start", {"total": len(self.phrases)}, "Okay, let's train your voice.")
            self._prompt()
            return "training"
        return None

    def _prompt(self):
        self.say("Training_Prompt", {"n": self.index + 1, "total": len(self.phrases), "phrase": self.phrases[self.index]},
                 "Say: %s" % self.phrases[self.index])

    # ---- every heard sentence while a session runs ----
    def hear(self, raw):
        """True if the sentence was part of the training (so the runner must not treat it as a command)."""
        if not self.active():
            return False
        if self.clock() > self.until:
            self._end("Training_Expired")
            return False
        heard = normalise(strip_name(raw))
        if not heard:
            return True
        self.until = self.clock() + SESSION_SECONDS
        if heard in CANCEL:
            self._end("Training_Cancel", finished=False)
            return True
        expected = self.phrases[self.index]
        if heard in SKIP:
            self.rows.append((expected, "", "skipped"))
            self.say("Training_Skip", {}, "Skipping that one.")
        else:
            self.rows.append((expected, heard, self._judge(expected, heard)))
        self.index += 1
        if self.index >= len(self.phrases):
            self._end("Training_Done")
        else:
            self._prompt()
        return True

    def _judge(self, expected, heard):
        target = normalise(expected)
        if heard == target:
            return "ok"
        if difflib.SequenceMatcher(None, heard, target).ratio() >= CLOSE_ENOUGH and self.learning is not None:
            from control.learning import PROMOTE_AFTER
            for _ in range(PROMOTE_AFTER):          # you read it out on purpose, so one go is enough
                self.learning.note(heard, target)
            return "learned"
        return "unclear"

    def _end(self, key, finished=True):
        counts = self.counts()
        where = self.write_report() if self.rows else ""
        self.history.extend(self.rows)
        self.index = -1
        self.say(key, {"ok": counts["ok"], "fixed": counts["learned"], "unclear": counts["unclear"], "where": where},
                 "Training finished.")

    def counts(self):
        counts = {"ok": 0, "learned": 0, "unclear": 0, "skipped": 0}
        for _e, _h, result in self.rows:
            counts[result] = counts.get(result, 0) + 1
        return counts

    # ---- the report ----
    def write_report(self):
        """Writes data/hearing_report.txt and returns a short place name for her to say."""
        rows = (self.history + self.rows)[-MAX_REPORT_ROWS:]
        model = self.settings.get("stt.model", "?")
        lines = ["Starling hearing report", "Made: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "Listening quality (stt.model): %s" % model, ""]
        total = len(rows) or 1
        ok = sum(1 for r in rows if r[2] == "ok")
        lines.append("Phrases: %d   heard right: %d (%d%%)   learned: %d   unclear: %d   skipped: %d" % (
            len(rows), ok, 100 * ok // total, sum(1 for r in rows if r[2] == "learned"),
            sum(1 for r in rows if r[2] == "unclear"), sum(1 for r in rows if r[2] == "skipped")))
        lines.append("")
        lines.append("asked for  ->  what she heard   [result]")
        for expected, heard, result in rows:
            lines.append("%s  ->  %s   [%s]" % (expected, heard or "-", result))
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            log.exception("Could not write the hearing report")
            return "it could not be saved"
        return "hearing_report.txt in your Starling data folder"
