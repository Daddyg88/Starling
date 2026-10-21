"""
The AskManager: Starling asks you a question out loud and listens for "yes" or "no".

Three kinds of question:
    fact   "Want to hear something interesting?"  (when you arrive in a system, as often as you choose)
    scan   "That one's worth a bit. Shall we go and scan it?"  (a valuable planet was found)
    bio    "Shall we go and see what's down there?"            (a planet with life was found: she only says it, no answer needed)

What your answer does to her mood (all with the usual soft caps, see config/mood_rules.json):
    fact   yes = a little better.  no = nothing, but turning her down three times in a row costs a little.
           saying nothing = a little worse.
    scan   yes = a little better.  no = nothing at all.  saying nothing = a little worse.
    bio    no answer is expected, so nothing changes her mood.

She only asks while she can actually hear you (listening is on), never during a safety warning,
never while your weapons are out, and never more than one question at a time.
"""

import re
import threading
import time
import random

from core.identity import personalise
from core.logger import get_logger
from personality import plans
from personality.answers import choose, classify, wants_a_fact
from personality.mood_engine import effective_mood

log = get_logger("ask")

FREQUENCY_MINUTES = {"rarely": 30, "sometimes": 15, "often": 8, "very_often": 4}
ARRIVAL_DELAY_SECONDS = 7.0          # wait a moment after arriving (and for the next jump to start)
MIN_GAP_SECONDS = 45.0               # never two questions closer than this
SAFE_AFTER_CRITICAL_SECONDS = 60.0
SCAN_COOLDOWN_SECONDS = 150.0
NEVER_SPOKEN_SECONDS = 45.0          # the question was queued but never spoken: forget it, no penalty
HARDPOINTS_BIT = 6
WORTH_SCANNING = ("Scan_EarthLike", "Scan_WaterWorld", "Scan_AmmoniaWorld", "Scan_GreenGasGiant", "Scan_Terraformable")
DECLINES_BEFORE_PENALTY = 3


class _Quiet(dict):
    def __missing__(self, key):
        return "that one"


class AskManager:
    def __init__(self, bus, speech, dialogue, settings, facts, state_provider=None, listening_provider=None,
                 clock=time.monotonic, rng=None, timer_factory=None, plot_provider=None):
        self.bus = bus
        self.plot_provider = plot_provider or (lambda system: (False, ""))   # copies a system name and runs the galaxy map macro
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.facts = facts
        self.state_provider = state_provider or (lambda: None)
        self.listening = listening_provider or (lambda: False)
        self.clock = clock
        self.rng = rng or random.Random()
        self.timer_factory = timer_factory or self._real_timer
        self._lock = threading.RLock()
        self.pending = None                 # the question waiting for an answer
        self._token = 0
        self._timers = {}
        self._last_asked = None
        self._last_fact_offer = None
        self._last_scan_offer = None
        self._asked_bodies = set()
        self._last_critical = None
        self.declines = 0                   # fact offers turned down or ignored in a row
        self._plan_asked = False            # 'What are we doing today?' is asked once per login
        self._midgame_tries = 0
        self.today = None                   # the activity you chose today (exploring, mining, ...)

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("*", self.on_event)

    def detach(self):
        self.bus.unsubscribe("*", self.on_event)

    @staticmethod
    def _real_timer(seconds, function):
        timer = threading.Timer(seconds, function)
        timer.daemon = True
        return timer

    def _start_timer(self, name, seconds, function):
        self._cancel_timer(name)
        timer = self.timer_factory(seconds, function)
        self._timers[name] = timer
        timer.start()

    def _cancel_timer(self, name):
        timer = self._timers.pop(name, None)
        if timer is not None:
            timer.cancel()

    # ---- settings ----
    def _can_chat(self):
        s = self.settings
        return bool(s.get("speech.enabled", True) and s.get("personality.style", "personality") == "personality"
                    and self.listening())

    def _mood(self):
        return effective_mood(self.settings)

    def _line(self, key, data=None):
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, self._mood(), allow, False)
        if line is None:
            return None
        text = line.text
        if "{" in text:
            try:
                text = text.format_map(_Quiet(data or {}))
            except (ValueError, IndexError):
                pass
        return personalise(text, self.settings)

    def _say(self, text, event_name):
        if not text or self.speech is None:
            return False
        return bool(self.speech.say(text=text, priority="normal", event_name=event_name))

    # ---- hearing the game ----
    def on_event(self, event):
        name = event.name
        try:
            if event.priority == "critical":
                self._last_critical = self.clock()
                self._drop_pending_quietly()        # a safety warning is more important than her question
            elif name == "LoadGame":
                self._logged_in()
            elif name == "FSDJump":
                self._arrived()
            elif name == "StartJump":
                self._cancel_timer("arrival")
            elif name == "Scan":
                self._maybe_scan(event.data or {})
            elif name in ("FSSBodySignals", "SAASignalsFound"):
                self._maybe_bio(event.data or {})
            elif name == "speech.finished":
                self._speech_finished(event.data or {})
        except Exception:
            log.exception("Ask manager problem with %s", name)

    def _calm_enough(self):
        now = self.clock()
        if self._last_critical is not None and now - self._last_critical < SAFE_AFTER_CRITICAL_SECONDS:
            return False
        if self._last_asked is not None and now - self._last_asked < MIN_GAP_SECONDS:
            return False
        state = self.state_provider()
        flags = getattr(state, "status_flags", None) if state is not None else None
        if flags is not None and (flags >> HARDPOINTS_BIT) & 1:
            return False
        return True

    def _may_ask(self):
        with self._lock:
            return self.pending is None and self._can_chat() and self._calm_enough()

    # ---- facts on arrival ----
    def _interval_seconds(self):
        minutes = FREQUENCY_MINUTES.get(str(self.settings.get("facts.frequency", "sometimes")))
        if minutes is None:
            return None                                    # off
        return minutes * 60.0 * min(3.0, 1.0 + 0.5 * self.declines)    # the more you decline, the less she asks

    def _arrived(self):
        interval = self._interval_seconds()
        if interval is None:
            return
        now = self.clock()
        if self._last_fact_offer is not None and now - self._last_fact_offer < interval:
            return
        self._start_timer("arrival", ARRIVAL_DELAY_SECONDS, self._offer_fact)

    def _offer_fact(self):
        if not self._may_ask():
            return
        self._last_fact_offer = self.clock()
        self._ask("fact", "Ask_FactOffer", {})

    # ---- valuable planets and life ----
    def _maybe_scan(self, data):
        if not self.settings.get("ask.scan_prompts", True):
            return
        from personality.line_keys import scan_keys
        keys = scan_keys(data)
        if not any(k in WORTH_SCANNING for k in keys):
            return
        if data.get("WasMapped"):
            return                                          # someone already mapped it: not worth a special trip
        body = data.get("BodyName") or ""
        now = self.clock()
        if body in self._asked_bodies:
            return
        if self._last_scan_offer is not None and now - self._last_scan_offer < SCAN_COOLDOWN_SECONDS:
            return
        if not self._may_ask():
            return
        self._asked_bodies.add(body)
        self._last_scan_offer = now
        self._ask("scan", "Ask_Scan", {"body": body})

    def _maybe_bio(self, data):
        """Life found: she wonders aloud if you want to go and look. No answer is listened for (it was too repetitive)."""
        if not self.settings.get("ask.bio_prompts", True) or not data.get("Biological"):
            return
        body = data.get("BodyName") or ""
        if ("bio", body) in self._asked_bodies:
            return
        s = self.settings
        if not (s.get("speech.enabled", True) and s.get("personality.style", "personality") == "personality"):
            return
        with self._lock:
            if self.pending is not None or not self._calm_enough():
                return
        self._asked_bodies.add(("bio", body))
        self._last_asked = self.clock()
        self._say(self._line("Ask_Bio", {"body": body}), "ask.bio")

    # ---- asking ----
    def _ask(self, kind, key, data):
        self._ask_text(kind, self._line(key, data), data)

    def _ask_text(self, kind, text, data):
        if not text:
            return
        with self._lock:
            self._token += 1
            token = self._token
            self.pending = {"kind": kind, "token": token, "open": False, "asked": self.clock(), "data": data}
            self._last_asked = self.clock()
        if not self._say(text, "ask.question"):
            with self._lock:
                self.pending = None
            return
        self._start_timer("spoken", NEVER_SPOKEN_SECONDS, lambda: self._forget(token))

    def _forget(self, token):
        with self._lock:
            if self.pending is not None and self.pending["token"] == token and not self.pending["open"]:
                self.pending = None

    def _drop_pending_quietly(self):
        with self._lock:
            self.pending = None
        self._cancel_timer("spoken")
        self._cancel_timer("answer")

    def _speech_finished(self, data):
        if data.get("event") == "login.greeting":
            self._cancel_timer("plan_fallback")
            self._start_timer("plan", 1.5, self.ask_plan)             # as soon as she has finished saying hello
            return
        if data.get("event") != "ask.question":
            return
        with self._lock:
            pending = self.pending
            if pending is None or pending["open"]:
                return
            pending["open"] = True
            token = pending["token"]
        self._cancel_timer("spoken")
        seconds = float(self.settings.get("ask.answer_seconds", 10) or 10)
        self._start_timer("answer", seconds, lambda: self._timed_out(token))

    def _timed_out(self, token):
        with self._lock:
            pending = self.pending
            if pending is None or pending["token"] != token:
                return
            self.pending = None
        self._finish(pending, "ignored")

    # ---- hearing you ----
    def handle_heard(self, text, wake, command, ptt=False):
        """Called by the ears before anything else. Returns True if this was an answer (or a fact request)."""
        spoken = (command if wake else text) or ""
        with self._lock:
            pending = self.pending if (self.pending and self.pending["open"]) else None
        if pending is not None:
            if pending["kind"] == "plan":
                answer = plans.topic_from(spoken)
            else:
                answer = choose(spoken) if pending["kind"] == "choice" else classify(spoken)
            if answer is not None:
                with self._lock:
                    if self.pending is not pending:
                        return False
                    self.pending = None
                self._cancel_timer("answer")
                self._finish(pending, answer)
                return True
        if (wake or ptt) and wants_a_fact(spoken) and self.settings.get("speech.enabled", True):
            self._tell_a_fact(now_asked=False)
            return True
        return False

    # ---- what happens next ----
    def _finish(self, pending, answer):
        kind = pending["kind"]
        data = pending.get("data") or {}
        if kind == "plan":
            self._finish_plan(answer, data)
            return
        if kind == "choice":
            self._finish_choice(answer, data)
            return
        if kind == "route":
            self._finish_route(answer, data)
            return
        if kind == "fact":
            self._finish_fact(answer)
            return
        if answer == "yes":
            self._say(self._line("Ask_ScanYes", data), "ask.reply")
            self._publish("ask.scan_yes", "Agreed to scan a planet")
        elif answer == "no":
            self._say(self._line("Ask_ScanNo", data), "ask.reply")
        else:
            if self.rng.random() < 0.5:
                self._say(self._line("Ask_Ignored", data), "ask.reply")
            self._publish("ask.scan_ignored", "Ignored a question about a planet")

    # ---- "What are we doing today?" ----
    def _logged_in(self):
        self._plan_asked = False
        self.today = None
        self._cancel_timer("midgame")
        self._start_timer("plan_fallback", 25.0, self.ask_plan)       # if she never says hello, ask anyway

    def schedule_midgame(self, active_provider, delay=30.0):
        """Starling started while you were already playing: there was no login, so ask a little after start-up."""
        self._active_provider = active_provider

        def check():
            if self._plan_asked:
                return
            try:
                active = bool(self._active_provider())
            except Exception:
                active = False
            if not active:
                return                                              # not in the game: the next login will ask
            if not self.ask_plan() and not self._plan_asked and self._midgame_tries < 4:
                self._midgame_tries += 1                              # ears or voice not ready yet: try again shortly
                self._start_timer("midgame", 20.0, check)
        self._start_timer("midgame", delay, check)

    def ask_plan(self):
        """Says 'What are we doing today?' and listens for an activity. Returns True if she asked."""
        if not self.settings.get("plans.ask", True):
            return False
        with self._lock:
            if self._plan_asked or self.pending is not None or not self._can_chat():
                return False
            if self._last_critical is not None and self.clock() - self._last_critical < SAFE_AFTER_CRITICAL_SECONDS:
                return False
        disliked = self.rng.choice(plans.TOPICS)                    # the ONE she is not in the mood for today
        text = self._line("Plan_Ask")
        if not text:
            return False
        self._plan_asked = True
        self._ask_text("plan", text, {"disliked": disliked})
        return True

    def _finish_plan(self, answer, data):
        topic = answer if answer in plans.TOPICS else None
        values = {"activity": plans.SPOKEN.get(topic, "")}
        if topic is None:
            if answer == "none":
                self._say(self._line("Plan_Open"), "ask.reply")
            return                                                    # no answer in time: nothing said, no points
        self.today = topic
        if topic == data.get("disliked"):
            self._say(self._line("Plan_Dislike_" + topic, values), "ask.reply")
            self._publish("plan.disliked", "Chose %s when she was not in the mood" % plans.SPOKEN[topic])
        else:
            self._say(self._line("Plan_Like_" + topic, values), "ask.reply")
            self._publish("plan.liked", "Chose %s and she was in the mood" % plans.SPOKEN[topic])

    # ---- where to sell: "A or B?" then "shall I plot a route?" ----
    @staticmethod
    def _option_values(option, suffix=""):
        tons = option.get("tons")
        if tons is None:
            tons = option.get("demand") or option.get("stock") or 0
        distance = option.get("distance")
        away = ("%d light years away" % int(round(distance))) if isinstance(distance, (int, float)) and distance >= 0.5 \
            else "right here in this system"
        return {"Price" + suffix: "{:,}".format(option["price"]), "Tons" + suffix: "{:,}".format(int(tons)),
                "Station" + suffix: option["station"], "System" + suffix: option["system"], "Away" + suffix: away}

    def offer_sale(self, material, options, order="best", mode="sell"):
        """She has found places to sell (or buy; mode="buy"). Says the best two (A and B) with price, tonnage and station, then asks which.
        Returns the words said (for the log). With one option she goes straight to asking about the route."""
        options = list(options or [])[:2]
        if not options:
            return None
        values = {"Material": material}
        values.update(self._option_values(options[0]))
        side = "Buy" if mode == "buy" else "Sell"
        near = order == "nearest"
        if len(options) > 1:
            values.update(self._option_values(options[1], "2"))
            head = self._line("%s_%sOptions" % (side, "Near" if near else ""), values)
        else:
            head = self._line("Sell_NearOne" if near and side == "Sell" else "%s_OneOption" % side, values)
        if not head:
            return None
        can_answer = self._can_chat()
        if not can_answer:
            self._say(head, "brain")                       # she can't hear you, so she only tells you
            return head.replace("||", " ")
        data = {"options": options, "material": material}
        if len(options) > 1:
            question = self._line("Sell_WhichOne", values)
            self._ask_text("choice", "%s||%s" % (head, question) if question else head, data)
        else:
            data = {"option": options[0], "material": material}
            question = self._line("Sell_RouteAsk", values)
            self._ask_text("route", "%s||%s" % (head, question) if question else head, data)
        return head.replace("||", " ")

    def _finish_choice(self, answer, data):
        options = data.get("options") or []
        if answer in ("A", "B"):
            index = 0 if answer == "A" else 1
            if index >= len(options):
                index = 0
            chosen = options[index]
            values = {"Material": data.get("material", ""), "Letter": answer}
            values.update(self._option_values(chosen))
            text = self._line("Sell_RouteAsk", values)
            self._ask_text("route", text, {"option": chosen, "material": data.get("material", ""), "Letter": answer})
        elif answer == "no":
            self._say(self._line("Sell_NoChoice"), "ask.reply")
        # no answer in time: she just drops it, nothing to say

    def _finish_route(self, answer, data):
        option = data.get("option") or {}
        values = {"Material": data.get("material", "")}
        values.update(self._option_values(option) if option else {})
        if answer == "yes":
            ok, reason = self.plot_provider(option.get("system"))
            if not ok:
                values["Reason"] = reason or "the galaxy map macro is not available"
                self._say(self._line("Sell_RouteOff", values), "ask.reply")
                return
            self._say(self._line("Sell_RouteYes", values), "ask.reply")
        elif answer == "no":
            self._say(self._line("Sell_RouteNo", values), "ask.reply")

    def _finish_fact(self, answer):
        if answer == "yes":
            self.declines = 0
            self._tell_a_fact(now_asked=True)
            self._publish("ask.fact_yes", "Wanted to hear a fact")
            return
        self.declines += 1
        if answer == "no":
            self._say(self._line("Ask_FactNo"), "ask.reply")
            if self.declines >= DECLINES_BEFORE_PENALTY:
                self._say(self._line("Ask_FactStreak"), "ask.reply")
                self._publish("ask.fact_streak", "Turned down facts too many times")
        else:
            if self.rng.random() < 0.6:
                self._say(self._line("Ask_Ignored"), "ask.reply")
            self._publish("ask.fact_ignored", "Ignored an offer of a fact")

    def _tell_a_fact(self, now_asked):
        topic = str(self.settings.get("facts.topics", "all"))
        fact = self.facts.next(topic) if self.facts is not None else None
        if not fact:
            return
        intro = self._line("Ask_FactYes") if now_asked else self._line("Ask_FactRequest")
        lead = self._line("Fact_Intro") or "Here's something I read."
        text = ("%s||%s||%s" % (intro, lead, fact)) if intro else ("%s||%s" % (lead, fact))
        self._say(text, "ask.fact")

    def _publish(self, name, summary):
        if self.bus is not None:
            self.bus.publish(name, {"summary": summary}, "low")
