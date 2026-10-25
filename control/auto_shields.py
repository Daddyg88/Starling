"""
Auto shields on foot: raise the suit shields when you pull a weapon out, or when you start taking damage.

How: Status.json says what you are holding (SelectedWeapon) and your health (Health, 0 to 1). When you go from "no weapon" to
"a weapon in hand", or your health drops while on foot, she presses your Toggle Shields key ONCE. When you put the weapon away she presses it again to lower them
(only if she was the one who raised them). In a fight she keeps them up: a combat bond or bounty on foot, or taking damage, starts
a 2 minute "combat zone" mode where she raises them if they are down and does NOT lower them when you holster.
The game has no "in a combat zone" flag, so those signs are the best she can see (she cannot raise them BEFORE the first one).

Honest limits (nobody has been able to check these against a live game yet):
  * The game has one Toggle Shields key, and nothing in Status.json or the journal says whether the shields are up. So she keeps
    her own count: after she raises them she will not press again until she lowers them (you holster) or you leave the suit.
    If your shields were already up when she pressed, they go DOWN. Say "suit shields" to flip them back.
  * What SelectedWeapon looks like for fists, tools and guns is read from the usual wording. Fists, tools and scanners are ignored.
  * The setting is OFF until you switch it on in the dashboard (On foot page).
"""

import time

from core.logger import get_logger

log = get_logger("autoshields")

ACTION = "HumanoidToggleShieldsButton"
ON_FOOT_BIT = 0                       # Status.json Flags2
NOT_WEAPONS = ("fists", "fist", "none", "tool", "scanner", "analyser", "analyzer", "recharge", "energylink", "energy link", "sampler")
COOLDOWN_SECONDS = 8.0
FIGHT_SECONDS = 120.0                 # after a combat sign, she treats you as "in a fight" this long
HURT_DROP = 0.02                      # health must fall by this much (of 1.0) to count as damage


def on_foot(state):
    flags2 = getattr(state, "status_flags2", 0) or 0
    return bool((flags2 >> ON_FOOT_BIT) & 1)


def weapon_in_hand(name):
    text = str(name or "").strip().lower()
    return bool(text) and not any(word in text for word in NOT_WEAPONS)


class AutoShields:
    def __init__(self, settings, book, sender, clock=time.monotonic):
        self.settings = settings
        self.book = book
        self.sender = sender
        self.clock = clock
        self._fight_until = 0.0       # "combat zone" mode lasts until this time (see mark_fight)
        self.up = False               # her own count (see the top of this file)
        self._armed = None            # was a weapon in hand last time?
        self._health = None
        self._last = None
        self.last_result = ""

    def enabled(self):
        return bool(self.settings.get("onfoot.auto_shields", False))

    def mark_fight(self):
        """A sign of combat on foot (a combat bond, a bounty, or damage). Keeps the shields up for a couple of minutes."""
        self._fight_until = self.clock() + FIGHT_SECONDS

    def fighting(self):
        return self.clock() < self._fight_until

    def on_combat_event(self, _event=None):
        """Bus handler for FactionKillBond / Bounty. Only counts when you are on foot."""
        if self._on_foot:
            self.mark_fight()

    _on_foot = False

    def check(self, state):
        """Called after every Status.json read."""
        self._on_foot = on_foot(state)
        if not self._on_foot:
            self.up, self._armed, self._health = False, None, None      # a new trip: forget her count
            self._fight_until = 0.0
            return
        armed = weapon_in_hand(getattr(state, "selected_weapon", ""))
        health = getattr(state, "health", None)
        reason = None
        if self._armed is not None and armed and not self._armed:
            reason = "weapon"
        elif (self._health is not None and isinstance(health, (int, float)) and self._health - health >= HURT_DROP):
            reason = "damage"
            self.mark_fight()
        self._armed = armed
        if isinstance(health, (int, float)):
            self._health = health
        if not self.enabled():
            if not armed:
                self.up = False
            return
        if reason:
            self._raise(reason)
        elif self.fighting() and not self.up:
            self._raise("combat zone")                      # in a fight: shields are kept up
        elif self.up and not armed and not self.fighting():
            self._lower()                                   # weapon away and no fight: shields down

    def _lower(self):
        """Weapon put away: if SHE raised the shields, press the key again to drop them."""
        if not self.up:
            self.last_result = "nothing to lower"
            return
        stroke, why = self.book.lookup(ACTION)
        if stroke is None:
            self.last_result = "unbound"
            self.up = False
            return
        problem = self.sender.send(stroke)
        self.last_result = problem or "lowered"
        if not problem:
            self.up = False
            log.info("Auto shields: weapon holstered, pressed the shields key to lower them")
        else:
            log.warning("Auto shields could not lower the shields: %s", problem)

    def _raise(self, reason):
        if self.up:
            self.last_result = "already up"
            return
        now = self.clock()
        if reason in ("damage", "combat zone") and self._last is not None and now - self._last < COOLDOWN_SECONDS:
            self.last_result = "too soon"
            return
        stroke, why = self.book.lookup(ACTION)
        if stroke is None:
            self.last_result = "unbound"
            log.warning("Auto shields: no keyboard key for %s (%s)", ACTION, why)
            return
        if reason in ("damage", "combat zone"):
            self._last = now
        problem = self.sender.send(stroke)
        self.last_result = problem or "done"
        if not problem:
            self.up = True
            log.info("Auto shields: pressed the shields key (%s)", reason)
        else:
            log.warning("Auto shields could not press the key: %s", problem)
