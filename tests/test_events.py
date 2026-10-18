import unittest

from core.event_bus import CRITICAL
from core.settings import load_event_config
from events.registry import load_registry
from tests.helpers import make_processor


class RegistryTests(unittest.TestCase):
    def test_every_configured_event_has_an_event_file(self):
        registry = load_registry()
        missing = [name for name in load_event_config() if name not in registry]
        self.assertEqual(missing, [], "events.json mentions events with no file")

    def test_every_event_file_has_a_name(self):
        for name, handler in load_registry().items():
            self.assertEqual(name, handler.name)

    def test_safety_events_are_critical(self):
        registry = load_registry()
        for name in ("LowFuel", "UnderAttack", "HullDamage", "ShieldState",
                     "MissionFailed", "Died", "Interdicted"):
            self.assertEqual(registry[name].priority, CRITICAL, name)


class ProcessorTests(unittest.TestCase):
    def test_fuel_scoop_line_becomes_an_event(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{ "timestamp":"x", "event":"FuelScoop", "Scooped":2.5, "Total":30.0 }')
        self.assertEqual(len(heard), 1)
        self.assertEqual(heard[0].name, "FuelScoop")
        self.assertIn("2.5", heard[0].data["summary"])

    def test_hull_damage_gets_a_percentage_and_updates_state(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"HullDamage","Health":0.42,"PlayerPilot":true,"Fighter":false}')
        self.assertEqual(heard[0].priority, CRITICAL)
        self.assertEqual(heard[0].data["Percent"], 42)
        self.assertAlmostEqual(processor.state.hull_health, 0.42)

    def test_unknown_events_are_ignored(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"Music","MusicTrack":"Combat"}')
        self.assertEqual(heard, [])
        self.assertEqual(processor.unknown_events, 1)

    def test_damaged_line_is_counted_not_fatal(self):
        processor, _bus, heard = make_processor()
        with self.assertLogs("starling.processor", level="WARNING"):
            processor.handle_line('{"event":"FuelScoop", "Scooped": ')
        self.assertEqual(heard, [])
        self.assertEqual(processor.damaged_lines, 1)

    def test_silent_mode_learns_but_does_not_announce(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"Commander","Name":"Ada"}', silent=True)
        processor.handle_line('{"event":"Docked","StationName":"Hutton","StarSystem":"Sol"}', silent=True)
        self.assertEqual(heard, [])
        self.assertEqual(processor.state.commander, "Ada")
        self.assertTrue(processor.state.docked)
        self.assertEqual(processor.state.system, "Sol")

    def test_loadout_teaches_fuel_capacity_without_speaking(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"Loadout","Ship":"anaconda","FuelCapacity":{"Main":32.0,"Reserve":1.0}}')
        self.assertEqual(heard, [])
        self.assertEqual(processor.state.fuel_capacity, 32.0)

    def test_low_priority_event_can_be_switched_off(self):
        config = {"FuelScoop": {"enabled": False, "priority": "low", "source": "journal"}}
        processor, _bus, heard = make_processor(config)
        processor.handle_line('{"event":"FuelScoop","Scooped":1,"Total":2}')
        self.assertEqual(heard, [])

    def test_critical_event_cannot_be_switched_off_or_downgraded(self):
        config = {"HullDamage": {"enabled": False, "priority": "low", "source": "journal"}}
        processor, _bus, heard = make_processor(config)
        processor.handle_line('{"event":"HullDamage","Health":0.1}')
        self.assertEqual(len(heard), 1)
        self.assertEqual(heard[0].priority, CRITICAL)

    def test_event_name_found_with_or_without_spaces(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event" : "Undocked", "StationName":"A"}')
        processor.handle_line('{"event":"Undocked","StationName":"B"}')
        self.assertEqual(len(heard), 2)

    def test_died_without_killer_still_makes_sense(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"Died"}')
        self.assertEqual(heard[0].data["summary"], "Ship destroyed")


if __name__ == "__main__":
    unittest.main()


class CompletenessTests(unittest.TestCase):
    def test_every_announced_event_can_be_controlled_in_events_json(self):
        config = load_event_config()
        missing = [n for n, h in load_registry().items() if h.announce and n not in config]
        self.assertEqual(missing, [], "add these to config/events.json")

    def test_status_events_have_the_status_source(self):
        registry = load_registry()
        for name in ("LandingGearDown", "HardpointsDeployed", "NightVisionOn", "GalaxyMapOpened", "LowOxygen"):
            self.assertEqual(registry[name].source, "status", name)

    def test_new_safety_events_are_critical(self):
        registry = load_registry()
        for name in ("HeatWarning", "HeatDamage", "CockpitBreached", "InterdictionInProgress",
                     "LowOxygen", "LowHealth", "VeryColdWarning", "VeryHotWarning"):
            self.assertEqual(registry[name].priority, CRITICAL, name)

    def test_ignored_events_are_counted_for_the_report(self):
        processor, _bus, _heard = make_processor()
        for _ in range(3):
            processor.handle_line('{"event":"ModuleInfo","TargetLocked":false}')
        processor.handle_line('{"event":"Music"}')
        self.assertEqual(processor.ignored_report(), ["ModuleInfo: 3", "Music: 1"])

    def test_exobiology_events(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"ScanOrganic","ScanType":"Sample","Species_Localised":"Fumerola Nitris"}')
        processor.handle_line('{"event":"SellOrganicData","BioData":[{"Value":1000,"Bonus":500},{"Value":200,"Bonus":0}]}')
        self.assertEqual(heard[0].data["summary"], "Sample 2 of 3: Fumerola Nitris")
        self.assertEqual(heard[1].data["TotalValue"], 1700)
        self.assertEqual(heard[1].data["Count"], 2)

    def test_biological_signals_are_counted(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"SAASignalsFound","BodyName":"A 1 a","Signals":['
                              '{"Type":"$SAA_SignalType_Biological;","Type_Localised":"Biological","Count":3},'
                              '{"Type":"$SAA_SignalType_Geological;","Type_Localised":"Geological","Count":1}]}')
        self.assertEqual((heard[0].data["Biological"], heard[0].data["Geological"]), (3, 1))
        self.assertIn("3 biological", heard[0].data["summary"])

    def test_new_status_events_exist(self):
        registry = load_registry()
        for name in ("FsdCharging", "FuelScoopStarted", "FuelScoopComplete", "VehicleChanged"):
            self.assertIn(name, registry)

    def test_new_journal_events_work(self):
        processor, _bus, heard = make_processor()
        processor.handle_line('{"event":"HeatWarning"}')
        processor.handle_line('{"event":"DockingGranted","StationName":"Hutton","LandingPad":7}')
        self.assertEqual([e.name for e in heard], ["HeatWarning", "DockingGranted"])
        self.assertEqual(heard[0].priority, CRITICAL)
        self.assertIn("pad 7", heard[1].data["summary"])
