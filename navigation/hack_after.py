"""AFTER A HACK (0.96.3): the story, the better mood and the next base to hack. Hangs on HackMode.on_complete.

Order: (1) only for a base that was properly mapped ("complete"): one chapter of her past, whatever her mood (personality/hack_lore.py);
(2) the mood boost (hack.mood, and only when her mood is not frozen); (3) the next target from Spansh (hack.next_target), looked up in a
thread so nothing waits. Each part is on its own try: one failing never stops the rest.
"""
import threading

from core.logger import get_logger

log = get_logger("hack_after")


class AfterHack:
    def __init__(self, settings, lore, mood, narrator, store, next_target=None, system_provider=None, spawn=None, points=6.0):
        self.settings = settings
        self.lore = lore
        self.mood = mood
        self.narrator = narrator
        self.store = store
        self.next_target = next_target
        self.system_provider = system_provider or (lambda: None)
        self.spawn = spawn or (lambda work: threading.Thread(target=work, daemon=True, name="hack-next").start())
        self.points = points

    def __call__(self, result):
        if result.get("how") != "complete":
            return
        try:
            if self.lore is not None:
                self.lore.tell(result.get("group"))
        except Exception:
            log.exception("The hack story failed")
        try:
            if self.mood is not None and self.settings.get("hack.mood", True):
                if self.mood.reward(self.points, "Base hack") and self.narrator is not None:
                    self.narrator.say("Hack_Reward", {})
        except Exception:
            log.exception("The hack mood boost failed")
        try:
            if self.next_target is not None and self.settings.get("hack.next_target", True):
                self.spawn(lambda: self._next(result))
        except Exception:
            log.exception("The next target could not start")

    def _next(self, result):
        try:
            done = {k for k, v in self.store.data.items() if v.get("done")}
            found = self.next_target.find(self.system_provider(), skip_markets=done)
            if found is None:
                self.narrator.say("Hack_NextNone", {})
                return
            self.narrator.say("Hack_Next", {"next_name": found["name"], "next_system": found["system"],
                                            "next_distance": found["distance"] if found["distance"] is not None else "some",
                                            "next_group": found["group"]})
        except Exception:
            log.exception("The next target failed")
