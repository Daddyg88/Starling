import json
import random
import unittest
from pathlib import Path

from core import paths
from events import fsd_jump
from navigation.voice import RouteVoice, is_caspian
from personality import line_keys
from personality.dialogue import DialogueManager
from journal.status_reader import StatusReader
from tests.helpers import make_processor
from tests.test_flavour import make


def jump(system="Sol"):
    return json.dumps({"event": "FSDJump", "StarSystem": system, "JumpDist": 8.0, "FuelUsed": 1.0, "FuelLevel": 20.0})


def scan(name="Sol A 1", discovered=True, gravity=4.9, kelvin=288.0):
    return json.dumps({"event": "Scan", "BodyName": name, "WasDiscovered": discovered, "SurfaceGravity": gravity,
                       "SurfaceTemperature": kelvin, "ScanType": "AutoScan"})


class GlideTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})
        self.glide = 1 << 12

    def start_glide(self):
        self.reader.handle_status({"Flags": 0, "Flags2": 0})
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": 0})
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": self.glide})

    def test_scan_remembers_gravity_in_g_and_temperature(self):
        self.processor.handle_line(scan("Planet 1", gravity=19.6133, kelvin=402.4))
        facts = self.processor.state.bodies["Planet 1"]
        self.assertAlmostEqual(facts["gravity"], 2.0, places=2)
        self.assertEqual(round(facts["temperature"]), 402)

    def test_glide_names_temperature_and_gravity_of_the_planet(self):
        self.processor.handle_line(scan("Planet 1", gravity=4.9, kelvin=288.0))
        self.processor.state.current_body = "Planet 1"
        self.start_glide()
        glides = [e for e in self.heard if e.name == "GlideStarted"]
        self.assertEqual(len(glides), 1)
        self.assertEqual(glides[0].data["temperature"], 288)
        self.assertEqual(glides[0].data["gravity"], "0.50")
        self.assertFalse(glides[0].data["heavy"])

    def test_glide_without_a_scan_still_says_glide(self):
        self.start_glide()
        glide = [e for e in self.heard if e.name == "GlideStarted"][0]
        self.assertNotIn("temperature", glide.data)
        self.assertEqual(line_keys.keys_for(glide), ["GlideStarted"])

    def test_heavy_world_uses_the_heavy_lines_first(self):
        self.processor.handle_line(scan("Big", gravity=29.4, kelvin=300))
        self.processor.state.current_body = "Big"
        self.start_glide()
        glide = [e for e in self.heard if e.name == "GlideStarted"][0]
        self.assertEqual(line_keys.keys_for(glide)[0], "GlideStarted_Heavy")

    def test_status_json_body_name_sets_the_current_body(self):
        self.reader.handle_status({"Flags": 1 << 24, "Flags2": 0, "BodyName": "Sol A 3"})
        self.assertEqual(self.processor.state.current_body, "Sol A 3")


class JumpCallouts(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()

    def names(self):
        return [e.name for e in self.heard]

    def test_scoopable_flag_for_each_star_class(self):
        start = self.processor.registry["StartJump"]
        for star, expected in (("G", True), ("M", True), ("O", True), ("N", False), ("H", False), ("L", False), ("D", False), ("T", False)):
            data = start.handle({"event": "StartJump", "JumpType": "Hyperspace", "StarClass": star})
            self.assertEqual(data["Scoopable"], expected, star)

    def test_scoop_keys(self):
        class E:
            name = "StartJump"
            def __init__(self, data): self.data = data
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace", "Scoopable": True})), ["StartJump_Scoop", "StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace", "Scoopable": False})), ["StartJump_NoScoop", "StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Hyperspace"})), ["StartJump"])
        self.assertEqual(line_keys.keys_for(E({"JumpType": "Supercruise", "Scoopable": True})), [])

    def test_first_scan_in_an_undiscovered_system_is_announced_once(self):
        self.processor.handle_line(jump("Nowhere"))
        self.processor.handle_line(scan("Nowhere A", discovered=False))
        self.processor.handle_line(scan("Nowhere B", discovered=False))
        found = [e for e in self.heard if e.name == "UndiscoveredSystem"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].data["StarSystem"], "Nowhere")

    def test_discovered_system_is_quiet(self):
        self.processor.handle_line(jump("Sol"))
        self.processor.handle_line(scan("Sol A", discovered=True))
        self.assertNotIn("UndiscoveredSystem", self.names())

    def test_replaying_old_journal_lines_is_silent(self):
        self.processor.handle_line(jump("Nowhere"), silent=True)
        self.processor.handle_line(scan("Nowhere A", discovered=False), silent=True)
        self.assertNotIn("UndiscoveredSystem", self.names())
        self.processor.handle_line(scan("Nowhere B", discovered=False))     # the flag was used up by the silent replay
        self.assertNotIn("UndiscoveredSystem", self.names())

    def test_jumps_left_said_when_the_dice_allow(self):
        old = fsd_jump.random.random
        fsd_jump.random.random = lambda: 0.0
        try:
            self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 5})
            self.processor.handle_line(jump())
        finally:
            fsd_jump.random.random = old
        left = [e for e in self.heard if e.name == "JumpsLeft"]
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0].data["jumps"], 5)
        self.assertEqual(line_keys.keys_for(left[0]), ["JumpsLeft"])

    def test_jumps_left_stays_quiet_when_the_dice_say_no(self):
        old = fsd_jump.random.random
        fsd_jump.random.random = lambda: 0.99
        try:
            self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 5})
            self.processor.handle_line(jump())
        finally:
            fsd_jump.random.random = old
        self.assertNotIn("JumpsLeft", self.names())

    def test_last_jump_is_always_mentioned_and_not_repeated(self):
        self.processor.handle_entry({"event": "FSDTarget", "Name": "X", "RemainingJumpsInRoute": 1})
        self.processor.handle_line(jump())
        self.processor.handle_line(jump("Elsewhere"))      # no new target: nothing more to say
        left = [e for e in self.heard if e.name == "JumpsLeft"]
        self.assertEqual(len(left), 1)
        self.assertEqual(line_keys.keys_for(left[0]), ["JumpsLeft_Last"])

    def test_no_route_no_callout(self):
        self.processor.handle_line(jump())
        self.assertNotIn("JumpsLeft", self.names())


class NomadTests(unittest.TestCase):
    def test_recovering_the_nomad_is_announced(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        srv = 1 << 26
        reader.handle_status({"Flags": 0})
        reader.handle_status({"Flags": 1 << 24})
        processor.state.in_nomad = True
        reader.handle_status({"Flags": srv})
        reader.handle_status({"Flags": 1 << 24})
        self.assertIn("NomadDocked", [e.name for e in heard])

    def test_recovering_a_normal_srv_is_not_the_nomad(self):
        processor, _bus, heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 0})
        reader.handle_status({"Flags": 1 << 24})
        reader.handle_status({"Flags": 1 << 26})
        reader.handle_status({"Flags": 1 << 24})
        self.assertNotIn("NomadDocked", [e.name for e in heard])


class CaspianTests(unittest.TestCase):
    class State:
        def __init__(self, ship=None, model=None):
            self.ship, self.ship_model = ship, model

    class Settings:
        def __init__(self, **values): self.values = values
        def get(self, key, default=None): return self.values.get(key, default)

    def voice(self, state, **values):
        values.setdefault("neutron.supercharge", 4)
        return RouteVoice(None, None, None, self.Settings(**values), lambda: state)

    def test_caspian_is_recognised_by_either_name(self):
        self.assertTrue(is_caspian(self.State("explorer_nx")))
        self.assertTrue(is_caspian(self.State("Caspian Explorer")))
        self.assertTrue(is_caspian(self.State(None, "Caspian Explorer")))
        self.assertFalse(is_caspian(self.State("anaconda", "Anaconda")))
        self.assertFalse(is_caspian(None))

    def test_x6_in_the_caspian_and_the_setting_elsewhere(self):
        self.assertEqual(self.voice(self.State("explorer_nx")).supercharge(), 6)
        self.assertEqual(self.voice(self.State("anaconda")).supercharge(), 4)
        self.assertEqual(self.voice(self.State("anaconda"), **{"neutron.supercharge": 6}).supercharge(), 6)

    def test_auto_x6_can_be_switched_off(self):
        self.assertEqual(self.voice(self.State("explorer_nx"), **{"neutron.auto_x6": False}).supercharge(), 4)


class PetNameTests(unittest.TestCase):
    def test_own_names_are_read_from_the_box(self):
        f, _d = make()
        f.settings.set("personality.custom_pet_names", "Captain Fluffy,  Sparky ;Boss\nNo. 1,, ")
        self.assertEqual(f.custom_names(), ["Captain Fluffy", "Sparky", "Boss", "No. 1"])

    def test_own_names_are_used(self):
        f, _d = make(roll=0.0)
        f.settings.set("personality.custom_pet_names", "Captain Fluffy")
        self.assertEqual(f.rename("Docked, Commander.", always=True), "Docked, Captain Fluffy.")

    def test_empty_box_changes_nothing(self):
        f, _d = make(roll=0.0)
        f.settings.set("personality.custom_pet_names", "")
        self.assertEqual(f.custom_names(), [])
        self.assertNotIn("Captain Fluffy", f.rename("Docked, Commander.", always=True))

    def test_rarely_used_when_she_is_upset(self):
        f, _d = make(mood="Upset", roll=0.5)
        f.settings.set("personality.custom_pet_names", "Captain Fluffy")
        self.assertNotIn("Captain Fluffy", f.rename("Docked, Commander.", always=True))


class DialogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()

    def test_every_new_key_has_lines(self):
        for key in ("GlideStarted_Info", "GlideStarted_Heavy", "StartJump_Scoop", "StartJump_NoScoop", "UndiscoveredSystem",
                    "JumpsLeft", "JumpsLeft_Last", "NomadDocked"):
            self.assertTrue(self.d.lines.get(key), key)

    def test_undiscovered_system_has_lots_of_lines(self):
        self.assertGreaterEqual(len(self.d.lines["UndiscoveredSystem"]), 50)

    def test_placeholders_are_known(self):
        allowed = {"FuelHalf": set(), "FuelPanic": {"fuel_percent"}, "LowFuel": {"fuel_percent"}, "GlideStarted": {"temperature", "gravity"}, "StartJump": {"StarSystem"}, "UndiscoveredSystem": {"StarSystem"},
                   "JumpsLeft": {"jumps"}, "NomadDocked": set()}
        import string
        for key, lines in self.d.lines.items():
            base = key.split("_")[0]
            if key.startswith(("FuelHalf", "FuelPanic", "LowFuel", "GlideStarted_", "StartJump_", "UndiscoveredSystem", "JumpsLeft", "NomadDocked")):
                for line in lines:
                    names = {f for _t, f, _s, _c in string.Formatter().parse(line.text) if f}
                    self.assertLessEqual(names, allowed[base], (key, line.text))

    def test_no_duplicate_lines_in_a_key(self):
        for key in ("UndiscoveredSystem", "StartJump_Scoop", "StartJump_NoScoop", "JumpsLeft", "GlideStarted_Info"):
            texts = [l.text for l in self.d.lines[key]]
            self.assertEqual(len(texts), len(set(texts)), key)


class BoostStars(unittest.TestCase):
    def test_neutron_and_white_dwarfs_are_boost_stars_not_fuel(self):
        from events.start_jump import StartJump
        h = StartJump()
        for star, boost in (("N", "neutron"), ("D", "whitedwarf"), ("DA", "whitedwarf"), ("DB", "whitedwarf")):
            data = h.handle({"JumpType": "Hyperspace", "StarClass": star})
            self.assertEqual(data["Boost"], boost, star)
            self.assertFalse(data["Scoopable"], star)
        self.assertNotIn("Boost", h.handle({"JumpType": "Hyperspace", "StarClass": "G"}))

    def test_boost_keys_come_first(self):
        class E:
            name = "StartJump"
            data = {"JumpType": "Hyperspace", "Scoopable": False, "Boost": "neutron"}
        self.assertEqual(line_keys.keys_for(E()), ["StartJump_Neutron", "StartJump_NoScoop", "StartJump"])
        E.data = {"JumpType": "Hyperspace", "Scoopable": False, "Boost": "whitedwarf"}
        self.assertEqual(line_keys.keys_for(E())[0], "StartJump_WhiteDwarf")


class FuelLevels(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.processor.state.fuel_capacity = 32.0
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})
        self.reader.handle_status({"Flags": 1 << 24, "Fuel": {"FuelMain": 32.0}})

    def fuel(self, tons, flags=1 << 24):
        self.reader.handle_status({"Flags": flags, "Fuel": {"FuelMain": tons}})

    def names(self):
        return [e.name for e in self.heard]

    def test_half_then_panic_each_once(self):
        self.fuel(20.0)
        self.assertEqual(self.names(), [])
        self.fuel(15.9)
        self.fuel(15.0)
        self.assertEqual(self.names(), ["FuelHalf"])
        self.fuel(3.0)
        self.fuel(2.9)
        self.assertEqual(self.names(), ["FuelHalf", "FuelPanic"])
        self.assertEqual(self.heard[-1].priority, "critical")

    def test_dropping_straight_to_panic_does_not_also_say_half(self):
        self.fuel(3.0)
        self.assertEqual(self.names(), ["FuelPanic"])

    def test_warnings_come_back_after_refuelling(self):
        self.fuel(15.0)
        self.fuel(30.0)
        self.fuel(15.0)
        self.assertEqual(self.names(), ["FuelHalf", "FuelHalf"])

    def test_quiet_when_docked(self):
        self.fuel(10.0, flags=(1 << 24) | 1)
        self.assertEqual(self.names(), [])

    def test_quiet_at_start_up(self):
        processor, _bus, heard = make_processor()
        processor.state.fuel_capacity = 32.0
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 1 << 24, "Fuel": {"FuelMain": 10.0}}, initial=True)
        reader.handle_status({"Flags": 1 << 24, "Fuel": {"FuelMain": 9.5}})
        self.assertEqual([e.name for e in heard], [])


class EchoMute(unittest.TestCase):
    def test_muted_events_stay_quiet_every_time_until_it_runs_out(self):
        from control.echo import Echo
        now = [0.0]
        echo = Echo(clock=lambda: now[0])
        echo.mute(("GalaxyMapOpened", "ScreenClosed"), 10)
        event = type("E", (), {"name": "ScreenClosed", "priority": "low"})()
        self.assertTrue(echo.consume(event))
        self.assertTrue(echo.consume(event))
        now[0] = 11
        self.assertFalse(echo.consume(event))

    def test_safety_events_are_never_muted(self):
        from control.echo import Echo
        echo = Echo()
        echo.mute(("LowFuel",), 10)
        self.assertFalse(echo.consume(type("E", (), {"name": "LowFuel", "priority": "critical"})()))


class RouteTargetTests(unittest.TestCase):
    class Settings:
        def __init__(self, **v): self.v = v
        def get(self, k, d=None): return self.v.get(k, d)

    class Narrator:
        def __init__(self): self.said = []
        def say(self, key, fields=None): self.said.append(key)

    class Follower:
        active = False

    def voice(self, target="", **settings):
        v = RouteVoice(self.Follower(), None, self.Narrator(), self.Settings(**settings), lambda: None, spawn=lambda f: None)
        v.game_target = lambda: target
        return v

    def test_plot_neutron_course_to_home_uses_the_home_bookmark(self):
        v = self.voice(**{"bookmarks.home": "Sol"})
        self.assertEqual(v.try_handle("plot neutron course to Home"), "Plotting a neutron route to Sol")

    def test_bare_plot_uses_the_destination_set_in_the_game(self):
        v = self.voice(target="Colonia")
        self.assertEqual(v.try_handle("plot a neutron route"), "Plotting a neutron route to Colonia")
        self.assertEqual(self.voice(target="Colonia").try_handle("plot neutron course"), "Plotting a neutron route to Colonia")

    def test_bare_plot_with_no_target_asks_where(self):
        v = self.voice(target="")
        self.assertEqual(v.try_handle("plot a neutron route"), "No destination.")

    def test_my_destination_prefers_the_game_target_then_the_dashboard_box(self):
        self.assertEqual(self.voice(target="Colonia", **{"neutron.destination": "Sag A*"}).try_handle("plot a neutron route to my destination"),
                         "Plotting a neutron route to Colonia")
        self.assertEqual(self.voice(target="").try_handle("plot a neutron route to my destination"), "No destination.")
        self.assertEqual(self.voice(target="", **{"neutron.destination": "Sag A*"}).try_handle("plot a neutron route to my destination"),
                         "Plotting a neutron route to Sag A*")

    def test_other_ways_to_ask(self):
        for said in ("plot neutron route", "start the neutron plotter", "neutron plotter", "plot neutron", "do the neutron plot"):
            self.assertEqual(self.voice(target="Colonia").try_handle(said), "Plotting a neutron route to Colonia", said)

    def test_automatic_plotting_is_off_unless_switched_on(self):
        v = self.voice(target="Colonia")
        v.spawn = lambda f: self.fail("should not plot by itself")
        v.on_nav_route()

    def test_next_waypoint_phrases_are_not_hijacked(self):
        v = self.voice(target="Colonia")
        self.assertIsNone(v.try_handle("plot the next neutron waypoint"))

    def test_navroute_file_gives_the_last_system(self):
        import tempfile
        from navigation.game_target import read_target
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(read_target(folder), "")
            Path(folder, "NavRoute.json").write_text(json.dumps({"Route": [{"StarSystem": "Sol"}, {"StarSystem": "Colonia"}]}))
            self.assertEqual(read_target(folder), "Colonia")
            Path(folder, "NavRoute.json").write_text("{damaged")
            self.assertEqual(read_target(folder), "")


class WaypointCount(unittest.TestCase):
    def test_count_phrase(self):
        import tempfile
        from navigation.route import RouteFollower

        class S:
            def get(self, k, d=None): return d
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFollower(None, S(), save_path=Path(folder, "r.json"))
            f.set_route([{"system": "A", "jumps": 3, "neutron": True}, {"system": "B", "jumps": 2, "neutron": True},
                         {"system": "C", "jumps": 1, "neutron": False}], "C")
            self.assertEqual(f.fields()["count"], "3 waypoints to go.")
            f.index = 2
            self.assertEqual(f.fields()["count"], "Last waypoint.")


if __name__ == "__main__":
    unittest.main()


class AutoOnTarget(unittest.TestCase):
    def make(self, target="Colonia", here="Sol", **settings):
        settings.setdefault("neutron.auto_on_target", True)
        v = RouteVoice(RouteTargetTests.Follower(), None, RouteTargetTests.Narrator(), RouteTargetTests.Settings(**settings),
                       lambda: type("S", (), {"system": here})(), spawn=lambda f: f())
        v.game_target = lambda: target
        v.sleep = lambda s: None
        v.plotted = []
        v.plot = lambda name: v.plotted.append(name)
        return v

    def test_setting_a_target_plots_it(self):
        v = self.make()
        v.on_nav_route()
        self.assertEqual(v.plotted, ["Colonia"])

    def test_same_target_is_not_plotted_twice(self):
        v = self.make()
        v.on_nav_route()
        v.on_nav_route()
        self.assertEqual(v.plotted, ["Colonia"])

    def test_off_switch_target_here_and_no_target(self):
        for v in (self.make(**{"neutron.auto_on_target": False}), self.make(target="Sol"), self.make(target="")):
            v.on_nav_route()
            self.assertEqual(v.plotted, [])

    def test_her_own_macro_is_ignored(self):
        v = self.make()
        v.follower.active = False
        v.narrator = RouteTargetTests.Narrator()
        v.prepare_plot()                   # the macro is about to run
        v.on_nav_route()
        self.assertEqual(v.plotted, [])

    def test_a_waypoint_of_the_current_route_is_ignored(self):
        v = self.make(target="Neutron B")
        v.follower.active = True
        v.follower.destination = "Colonia"
        v.follower.waypoints = [{"system": "Neutron B"}]
        v.on_nav_route()
        self.assertEqual(v.plotted, [])


class MineralList(unittest.TestCase):
    def test_dropdown_lists_every_mineral_and_keeps_old_choices(self):
        from mining import minerals
        from ui.settings_model import MINERAL_CHOICES
        keys = [k for _l, k in MINERAL_CHOICES]
        self.assertEqual(MINERAL_CHOICES[0], ("(nothing)", ""))
        self.assertEqual(len(keys), len(set(keys)))
        for old in ("platinum", "painite", "opal", "lowtemperaturediamond", "monazite", "musgravite", "serendibite",
                    "grandidierite", "alexandrite", "rhodplumsite", "osmium", "palladium", "bromellite", "benitoite",
                    "gold", "silver", "cobalt", "bertrandite", "indite", "gallite", "uraninite", "praseodymium",
                    "samarium", "lithium", "tritium"):
            self.assertIn(old, keys)
        for new in ("cryolite", "taaffeite", "jadeite", "thorium", "titanium", "methaneclathrate", "water", "hafnium"):
            self.assertIn(new, keys)
        self.assertGreaterEqual(len(keys), 50)

    def test_new_minerals_can_be_named_in_speech(self):
        from mining import minerals
        self.assertEqual(minerals.from_speech("where do I sell the cryolite"), "cryolite")
        self.assertEqual(minerals.from_speech("sell my taaffeite"), "taaffeite")
        self.assertEqual(minerals.from_speech("sell the void opals"), "opal")
        self.assertEqual(minerals.spoken("lithiumhydroxide"), "Lithium Hydroxide")

    def test_a_new_favourite_is_exciting(self):
        from mining import minerals
        class S:
            def get(self, k, d=None): return "cryolite" if k == "mining.fav1" else None
        before = minerals._settings
        minerals.bind(S())
        try:
            self.assertEqual(minerals.tier("Cryolite"), "top")
        finally:
            minerals.bind(before)
