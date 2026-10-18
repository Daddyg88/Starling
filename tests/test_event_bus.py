import unittest

from core.event_bus import ALL_EVENTS, CRITICAL, EventBus


class EventBusTests(unittest.TestCase):
    def test_listener_receives_event(self):
        bus, seen = EventBus(), []
        bus.subscribe("FuelScoop", seen.append)
        bus.publish("FuelScoop", {"amount": 5})
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].data["amount"], 5)

    def test_other_events_are_ignored(self):
        bus, seen = EventBus(), []
        bus.subscribe("FuelScoop", seen.append)
        bus.publish("Docked")
        self.assertEqual(seen, [])

    def test_wildcard_hears_everything(self):
        bus, seen = EventBus(), []
        bus.subscribe(ALL_EVENTS, seen.append)
        bus.publish("Docked")
        bus.publish("FSDJump")
        self.assertEqual([e.name for e in seen], ["Docked", "FSDJump"])

    def test_broken_listener_does_not_stop_others(self):
        bus, seen = EventBus(), []

        def broken(event):
            raise RuntimeError("oops")

        bus.subscribe("Docked", broken)
        bus.subscribe("Docked", seen.append)
        with self.assertLogs("starling.event_bus", level="ERROR"):
            bus.publish("Docked")
        self.assertEqual(len(seen), 1)
        self.assertEqual(bus.handler_errors, 1)

    def test_unsubscribe(self):
        bus, seen = EventBus(), []
        bus.subscribe("Docked", seen.append)
        bus.unsubscribe("Docked", seen.append)
        bus.publish("Docked")
        self.assertEqual(seen, [])

    def test_priority_is_kept_and_checked(self):
        bus = EventBus()
        self.assertEqual(bus.publish("HullDamage", priority=CRITICAL).priority, CRITICAL)
        with self.assertRaises(ValueError):
            bus.publish("Docked", priority="whenever")


if __name__ == "__main__":
    unittest.main()
