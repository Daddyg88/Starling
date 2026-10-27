"""
THE UNANSWERED LIST - questions she could not answer.

Every time she says "I don't know that one", the question is counted in data/unanswered_questions.json (on your PC only).
Send me that file with your logs and the common ones become facts she knows. Say "what couldn't you answer?" and she reads out
the three she has been asked most.
"""

import json
import os
import re
import tempfile
import threading
from datetime import date

from core.logger import get_logger

log = get_logger("unanswered")

MAX_QUESTIONS = 300
ASK = re.compile(r"\b(?:what|which)(?: questions?| things?)? (?:could ?n.?t|can.?t|did ?n.?t|couldnt|cant|didnt) (?:you )?(?:answer|know)\b|"
                 r"\bwhat (?:have )?(?:i|we|people|chat) asked (?:you )?(?:that )?(?:you )?(?:could ?n.?t|didnt|did not) (?:answer|know)\b|"
                 r"\bwhat do you not know\b|\bwhat (?:are )?(?:the )?(?:questions )?you (?:do ?n.?t|dont|do not) know\b")


class Unanswered:
    def __init__(self, path):
        self.path = path
        self.items = {}
        self._lock = threading.Lock()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.items = {str(k): v for k, v in data.items() if isinstance(v, dict) and v.get("n")}
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("Could not read %s; starting an empty list", path)

    def add(self, question):
        key = re.sub(r"\s+", " ", str(question or "").lower()).strip()
        if len(key) < 6 or len(key) > 120:
            return
        with self._lock:
            item = self.items.setdefault(key, {"n": 0, "last": ""})
            item["n"] += 1
            item["last"] = date.today().isoformat()
            if len(self.items) > MAX_QUESTIONS:             # forget the oldest question that was only asked once
                oldest = min((k for k, v in self.items.items() if v["n"] == 1), key=lambda k: self.items[k]["last"], default=None)
                if oldest:
                    self.items.pop(oldest, None)
            self._save()

    def top(self, count=3):
        ranked = sorted(self.items.items(), key=lambda pair: (-pair[1]["n"], pair[1]["last"]))
        return [question for question, _ in ranked[:count]]

    def clear(self):
        with self._lock:
            self.items = {}
            try:
                os.remove(self.path)
            except OSError:
                pass

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(self.items, out, indent=1, ensure_ascii=False)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the unanswered list")
