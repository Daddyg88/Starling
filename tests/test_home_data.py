"""The Home page numbers and words (worked out without a window)."""
import unittest
from datetime import datetime
from types import SimpleNamespace

from events.system_facts import remember_system_facts
from journal.game_state import GameState
from ui import status
from ui.status import EventFeed, elite_date, home_data, kind_of, population_text


class Bus:
    def subscribe(self, *_):
        pass


class Settings:
    def get(self, key, default=None):
        return default


class HelperTests(unittest.TestCase):
    def test_population_words(self):
        self.assertEqual(population_text(12400000), "12.4 million")
        self.assertEqual(population_text(2000000000), "2 billion")
        self.assertEqual(population_text(0), "Uninhabited")
        self.assertEqual(population_text(None), "-")
        self.assertEqual(population_text(850), "850")

    def test_elite_date_adds_1286_years(self):
        self.assertEqual(elite_date(datetime(2026, 1, 24)), "24 JAN 3312")
        self.assertEqual(elite_date(datetime(2024, 2, 29)), "28 FEB 3310")

    def test_kind_of_known_names(self):
        for name, kind in status.KIND_BY_NAME.items():
            self.assertEqual(kind_of(name), kind)
        self.assertIsInstance(kind_of("SomethingOdd"), str)

    def test_feed_keeps_kinds_and_clears(self):
        feed = EventFeed(Bus())
        feed.on_event(SimpleNamespace(name="FSDJump", data={"summary": "Jumped"}, priority="low"))
        rows = feed.recent_with_kind()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "Jumped")
        feed.clear()
        self.assertEqual(feed.recent_with_kind(), [])


class SystemFactsTests(unittest.TestCase):
    def test_reads_security_allegiance_population(self):
        state = GameState()
        remember_system_facts({"SystemSecurity": "$SYSTEM_SECURITY_low;", "SystemAllegiance": "", "Population": 12400000}, state)
        self.assertEqual(state.system_security, "Low Security")
        self.assertEqual(state.system_allegiance, "Independent")
        self.assertEqual(state.system_population, 12400000)

    def test_localised_text_wins(self):
        state = GameState()
        remember_system_facts({"SystemSecurity_Localised": "High Security", "SystemAllegiance": "Federation"}, state)
        self.assertEqual(state.system_security, "High Security")
        self.assertEqual(state.system_allegiance, "Federation")


class HomeDataTests(unittest.TestCase):
    def app(self, state):
        return SimpleNamespace(state=state, settings=Settings(), mood=None, providers=None, listener=None, monitor=None)

    def test_never_raises_on_empty_state(self):
        data = home_data(self.app(GameState()), datetime(2026, 1, 24, 18, 27))
        self.assertEqual(data["time"], "18:27")
        self.assertEqual(len(data["tiles"]), 3)
        self.assertEqual(data["system"]["name"], "-")

    def test_ship_numbers(self):
        state = GameState()
        state.system = "Sol"
        state.cargo_tons, state.cargo_capacity = 12, 32
        data = home_data(self.app(state), datetime(2026, 1, 24, 18, 27))
        self.assertEqual(data["ship"]["cargo_text"], "12 / 32 T")
        self.assertAlmostEqual(data["ship"]["cargo"], 12 / 32.0, places=2)
        self.assertEqual(data["system"]["name"], "Sol")


if __name__ == "__main__":
    unittest.main()


class MicBoxTests(unittest.TestCase):
    def app(self, listener, ptt=None, mode="off"):
        class S:
            def get(self, key, default=None):
                return {"ptt.mode": mode}.get(key, default)
        return SimpleNamespace(listener=listener, ptt=ptt, settings=S())

    def listener(self, ready=True, failed=None):
        import threading
        event = threading.Event()
        if ready:
            event.set()
        return SimpleNamespace(ready=event, failed_reason=failed)

    def test_states(self):
        from ui.status import mic_state
        self.assertEqual(mic_state(self.app(None)), ("MIC OFF", "muted"))
        self.assertEqual(mic_state(self.app(self.listener(failed="no mic")))[1], "bad")
        self.assertEqual(mic_state(self.app(self.listener(ready=False)))[1], "warn")
        self.assertEqual(mic_state(self.app(self.listener())), ("LISTENING", "good"))

    def test_push_to_talk_lights_only_while_the_mic_is_open(self):
        from ui.status import mic_state
        closed = SimpleNamespace(is_open=lambda: False)
        opened = SimpleNamespace(is_open=lambda: True)
        self.assertEqual(mic_state(self.app(self.listener(), closed, "toggle")), ("PUSH TO TALK", "muted"))
        self.assertEqual(mic_state(self.app(self.listener(), opened, "toggle")), ("LISTENING", "good"))


class ShipModelTests(unittest.TestCase):
    def test_model_is_shown_next_to_your_own_name(self):
        state = GameState()
        state.ship, state.ship_name, state.ship_model = "explorer_nx", "Pooh bear", "Caspian Explorer"
        app = SimpleNamespace(state=state, settings=Settings(), mood=None, providers=None, listener=None, monitor=None)
        ship = home_data(app)["ship"]
        self.assertEqual((ship["name"], ship["model"]), ("Pooh bear", "Caspian Explorer"))

    def test_model_comes_from_the_code_when_the_game_gave_no_name(self):
        state = GameState()
        state.ship = "explorer_nx"
        app = SimpleNamespace(state=state, settings=Settings(), mood=None, providers=None, listener=None, monitor=None)
        self.assertEqual(home_data(app)["ship"]["model"], "Caspian Explorer")
