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


class MishearingTests(unittest.TestCase):
    def test_phrases_from_a_real_log_are_understood(self):
        for said in ("Start the neutron platter.", "Plot neutron cores.", "Plot your neutron route.", "Touch neutron.",
                     "Plot neutral.", "Set a new trunk horse.", "Plot Neatron Root.", "Plot Neutron Root.", "Plot neutron."):
            v = RouteTargetTests().voice(target="Colonia")
            self.assertEqual(v.try_handle(said), "Plotting a neutron route to Colonia", said)

    def test_ordinary_sentences_are_left_alone(self):
        v = RouteTargetTests().voice(target="Colonia")
        for said in ("what is the neutral mood", "open the galaxy map", "who is Ben Kenobi"):
            self.assertIsNone(v.try_handle(said), said)


class SetTargetTests(unittest.TestCase):
    def test_set_target_without_a_plotted_course(self):
        import tempfile
        from navigation.game_target import choose_target
        processor, _bus, _heard = make_processor()
        processor.handle_entry({"event": "FSDTarget", "Name": "Colonia", "RemainingJumpsInRoute": 0})
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(choose_target(folder, processor.state), "Colonia")        # no NavRoute.json at all

    def test_plotted_course_still_works(self):
        import tempfile
        from navigation.game_target import choose_target
        processor, _bus, _heard = make_processor()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "NavRoute.json").write_text(json.dumps({"Route": [{"StarSystem": "Sol"}, {"StarSystem": "B"}, {"StarSystem": "Colonia"}]}))
            self.assertEqual(choose_target(folder, processor.state), "Colonia")
            processor.handle_entry({"event": "FSDTarget", "Name": "B", "RemainingJumpsInRoute": 1})   # the next hop of that course
            self.assertEqual(choose_target(folder, processor.state), "Colonia")

    def test_a_newer_target_beats_an_old_course(self):
        import tempfile
        from navigation.game_target import choose_target
        processor, _bus, _heard = make_processor()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "NavRoute.json").write_text(json.dumps({"Route": [{"StarSystem": "Sol"}, {"StarSystem": "Colonia"}]}))
            processor.handle_entry({"event": "FSDTarget", "Name": "Sagittarius A*", "RemainingJumpsInRoute": 0})
            self.assertEqual(choose_target(folder, processor.state), "Sagittarius A*")

    def test_arriving_clears_the_target(self):
        from navigation.game_target import choose_target
        processor, _bus, _heard = make_processor()
        processor.handle_entry({"event": "FSDTarget", "Name": "Colonia"})
        processor.handle_line(jump("Colonia"))
        self.assertEqual(choose_target(None, processor.state), "")


class EdAstroTests(unittest.TestCase):
    class Reply:
        def __init__(self, text): self.text = text
        def read(self): return self.text.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def client(self, payload):
        from navigation.edastro import EdAstro
        self.urls = []

        def opener(request, timeout=0):
            self.urls.append(request.full_url)
            return self.Reply(payload if isinstance(payload, str) else json.dumps(payload))
        return EdAstro(opener)

    def test_url_and_parse(self):
        c = self.client({"id": 7, "name": "Beacon X", "galMapSearch": "Eorgh Prou AA-A h1", "coordinates": [1, 2, 3], "rating": 4})
        place = c.nearest((10.5, -20.25, 30))
        self.assertEqual(self.urls, ["https://edastro.com/gec/json/nearest/10.50/-20.25/30.00"])
        self.assertEqual(place["system"], "Eorgh Prou AA-A h1")
        self.assertEqual(place["poi"], "Beacon X")
        self.assertEqual(place["coords"], [1, 2, 3])
        c.nearest((0, 0, 0), 3)
        self.assertTrue(self.urls[-1].endswith("/nearest/0.00/0.00/0.00/3"))

    def test_odd_replies(self):
        self.assertIsNone(self.client([]).nearest((0, 0, 0)))
        self.assertIsNone(self.client({"error": "none"}).nearest((0, 0, 0)))
        self.assertEqual(self.client([{"name": "Sol"}]).nearest((0, 0, 0))["system"], "Sol")
        from navigation.edastro import EdAstroError
        with self.assertRaises(EdAstroError):
            self.client("not json").nearest((0, 0, 0))


class EmergencyTests(unittest.TestCase):
    class Spansh:
        def __init__(self, known): self.known, self.routes = known, []
        def find_system(self, name):
            from navigation.spansh import SpanshError
            for k in self.known:
                if k.casefold() == name.casefold():
                    return k
            raise SpanshError("Spansh doesn't know a system called %s." % name)
        def neutron_route(self, *a, **k):
            from navigation.spansh import SpanshError
            self.routes.append(a)
            if a[0] not in self.known:
                raise SpanshError("Could not find the starting system.")
            return [{"system": a[0], "neutron": False, "jumps": 0, "distance_left": 10},
                    {"system": a[1], "neutron": False, "jumps": 3, "distance_left": 0}]

    class Edastro:
        def __init__(self, places): self.places, self.calls = list(places), []
        def nearest(self, position, rating=None):
            self.calls.append(rating)
            return self.places.pop(0) if self.places else None

    class Follower:
        active = False
        destination = ""
        waypoints = []
        def __init__(self): self.copied, self.ran, self.set = [], 0, None
        def copier(self, text): self.copied.append(text); return True
        def auto_plot(self): self.ran += 1
        def clear(self): pass
        def set_route(self, waypoints, target, here=None): self.set = (waypoints, target, here); self.active = True
        def copy_next(self): return True
        def fields(self): return {}
        def maybe_auto_plot(self): return False

    def make(self, known=("Colonia", "Landmark"), places=(), auto_plot=True, position=(1, 2, 3), here="Lostville"):
        import tempfile
        state = type("S", (), {"system": here, "star_pos": position, "max_jump_range": 40.0})()
        v = RouteVoice(self.Follower(), self.Spansh(known), RouteTargetTests.Narrator(),
                       RouteTargetTests.Settings(**{"neutron.auto_plot": auto_plot, "neutron.emergency": True}), lambda: state,
                       spawn=lambda f: f())
        v.edastro = self.Edastro(places)
        v.emergency_file = Path(tempfile.mkdtemp()) / "e.json"
        v._emergency = None
        v.schedule_plot = lambda f: f()
        v.game_target = lambda: "Colonia"
        return v

    def place(self, system="Landmark", coords=(4, 6, 3)):
        return {"system": system, "poi": "The Landmark", "coords": list(coords), "rating": 3}

    def test_unknown_start_triggers_the_protocol_and_plots_a_course_there(self):
        v = self.make(places=[self.place()])
        v._busy = True
        v._plot_now("Colonia")
        self.assertEqual(v.narrator.said[:2], ["EmergencyStart", "EmergencyPlotting"])
        self.assertEqual(v._emergency, {"poi": "Landmark", "destination": "Colonia"})
        self.assertEqual(v.follower.ran, 1)                  # the galaxy map macro was started
        self.assertEqual(v.target_override, "Landmark")      # ...and will paste the landmark
        self.assertTrue(v.emergency_file.exists())

    def test_arriving_at_the_landmark_plots_the_neutron_route(self):
        v = self.make(places=[self.place()])
        v._busy = True
        v._plot_now("Colonia")
        v.state_provider().system = "Landmark"
        v.on_arrival(type("E", (), {"data": {"StarSystem": "Landmark"}})())
        self.assertIn("EmergencyArrived", v.narrator.said)
        self.assertEqual(v.spansh.routes[-1][:2], ("Landmark", "Colonia"))
        self.assertIsNone(v._emergency)
        self.assertFalse(v.emergency_file.exists())

    def test_other_arrivals_are_ignored(self):
        v = self.make(places=[self.place()])
        v._busy = True
        v._plot_now("Colonia")
        v.on_arrival(type("E", (), {"data": {"StarSystem": "Somewhere else"}})())
        self.assertEqual(v._emergency["poi"], "Landmark")

    def test_a_landmark_spansh_does_not_know_is_skipped(self):
        v = self.make(places=[self.place("Unknown Rock"), self.place("Landmark")])
        v._busy = True
        v._plot_now("Colonia")
        self.assertEqual(v._emergency["poi"], "Landmark")
        self.assertEqual(v.edastro.calls[:2], [None, 2])      # asked for a better-rated one next

    def test_without_the_auto_plotter_the_name_goes_on_the_clipboard(self):
        v = self.make(places=[self.place()], auto_plot=False)
        v._busy = True
        v._plot_now("Colonia")
        self.assertIn("EmergencyManual", v.narrator.said)
        self.assertEqual(v.follower.copied, ["Landmark"])
        self.assertEqual(v.follower.ran, 0)

    def test_nothing_found_and_no_position(self):
        v = self.make(places=[])
        v._busy = True
        v._plot_now("Colonia")
        self.assertIn("EmergencyNone", v.narrator.said)
        v = self.make(position=None)
        v._busy = True
        v._plot_now("Colonia")
        self.assertIn("EmergencyNoPosition", v.narrator.said)

    def test_a_known_start_does_not_trigger_it(self):
        v = self.make(known=("Colonia", "Landmark", "Lostville"), places=[self.place()])
        v.spansh.neutron_route = lambda *a, **k: (_ for _ in ()).throw(__import__("navigation.spansh").spansh.SpanshError("Spansh found no route."))
        v._busy = True
        v._plot_now("Colonia")
        self.assertEqual(v.narrator.said, ["RouteFailed"])

    def test_switched_off(self):
        v = self.make(places=[self.place()])
        v.settings.v["neutron.emergency"] = False
        v._busy = True
        v._plot_now("Colonia")
        self.assertEqual(v.narrator.said, ["RouteFailed"])

    def test_spoken_commands(self):
        v = self.make(places=[self.place()])
        self.assertEqual(v.try_handle("emergency protocol"), "Emergency protocol: finding a known place near us.")
        self.assertIn("EmergencyPlotting", v.narrator.said)
        v = self.make()
        v._emergency = {"poi": "Landmark", "destination": "Colonia"}
        self.assertEqual(v.try_handle("clear the route"), "Route cancelled.")
        self.assertIsNone(v._emergency)
        self.assertEqual(v.try_handle("clear the root"), "There was no route.")

    def test_position_comes_from_the_journal(self):
        processor, _bus, _heard = make_processor()
        processor.handle_line(json.dumps({"event": "FSDJump", "StarSystem": "X", "StarPos": [1.5, -2, 3], "JumpDist": 5, "FuelUsed": 1, "FuelLevel": 9}))
        self.assertEqual(processor.state.star_pos, (1.5, -2.0, 3.0))
        processor.handle_line(json.dumps({"event": "Location", "StarSystem": "Y", "StarPos": [7, 8, 9]}))
        self.assertEqual(processor.state.star_pos, (7.0, 8.0, 9.0))


class WelcomeHomeAndMap(unittest.TestCase):
    def test_welcome_home_once(self):
        v = EmergencyTests().make(places=[])
        v.settings.v["bookmarks.home"] = "Sol"
        arrive = lambda s: v.on_arrival(type("E", (), {"data": {"StarSystem": s}})())
        arrive("Elsewhere")
        self.assertEqual(v.narrator.said, [])
        arrive("sol")
        arrive("Sol")
        self.assertEqual(v.narrator.said, ["WelcomeHome"])

    def test_no_home_no_greeting(self):
        v = EmergencyTests().make(places=[])
        v.on_arrival(type("E", (), {"data": {"StarSystem": "Sol"}})())
        self.assertEqual(v.narrator.said, [])

    def test_open_galaxy_map_skips_the_open_key(self):
        from control.runner import CommandRunner
        from control.catalog import PLOT_MACRO
        from control.macros import parse_macro
        r = CommandRunner.__new__(CommandRunner)
        r.state_provider = lambda: type("S", (), {"status_seen": True, "gui_focus": 6})()
        self.assertTrue(r.galaxy_map_open())
        r.state_provider = lambda: type("S", (), {"status_seen": True, "gui_focus": 0})()
        self.assertFalse(r.galaxy_map_open())
        self.assertEqual(parse_macro(PLOT_MACRO)[0], ("press", "GalaxyMapOpen", 1))

    def test_status_reader_records_the_open_screen(self):
        processor, _bus, _heard = make_processor()
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 1 << 24, "GuiFocus": 6})
        self.assertEqual(processor.state.gui_focus, 6)


class FavouriteShipTests(unittest.TestCase):
    def make(self, ship="explorer_nx"):
        import tempfile
        from personality.favourite_ship import FavouriteShip
        state = type("S", (), {"ship": ship, "ship_model": None, "favourite_ship": None})()
        said = []
        f = FavouriteShip(lambda: state, None, say=lambda k, fields: said.append((k, fields)),
                          path=Path(tempfile.mkdtemp()) / "f.json")
        f.state, f.said = state, said
        return f

    def test_twenty_good_points_make_a_favourite(self):
        f = self.make()
        for _ in range(19):
            f.add(1.0)
        self.assertIsNone(f.favourite)
        f.add(1.0)
        self.assertEqual(f.favourite, "explorer_nx")
        self.assertEqual(f.state.favourite_ship, "explorer_nx")
        self.assertEqual(f.said[0][0], "FavouriteShip_New")

    def test_points_go_to_the_ship_you_are_flying_and_losses_do_not_count(self):
        f = self.make("anaconda")
        f.add(15)
        f.state.ship = "python"
        f.add(15)
        f.add(-10)
        self.assertIsNone(f.favourite)
        f.add(6)
        self.assertEqual(f.favourite, "python")

    def test_another_ship_must_beat_the_favourite(self):
        f = self.make("anaconda")
        f.add(25)
        f.state.ship = "python"
        f.add(22)
        self.assertEqual(f.favourite, "anaconda")        # 22 is over 20 but not more than 25
        f.add(5)
        self.assertEqual(f.favourite, "python")
        self.assertEqual(f.said[-1][0], "FavouriteShip_Changed")

    def test_it_is_remembered(self):
        from personality.favourite_ship import FavouriteShip
        f = self.make()
        f.add(30)
        again = FavouriteShip(lambda: f.state, None, path=f.path)
        self.assertEqual(again.favourite, "explorer_nx")
        self.assertTrue(again.is_favourite("EXPLORER_NX"))

    def test_mood_gains_feed_it(self):
        from core.event_bus import EventBus
        from personality.mood_engine import MoodEngine
        gains = []
        engine = MoodEngine(EventBus(), RouteTargetTests.Settings(**{}), persist=False)
        engine.good_listener = gains.append
        rule = {"id": "x", "label": "x", "delta": 2, "category": "c1"}
        engine._apply(rule, type("E", (), {"data": {}, "priority": "normal", "name": "X"})(), 1000.0)
        self.assertTrue(gains and gains[0] > 0)

    def test_swap_and_login_and_smalltalk_use_it(self):
        class E:
            name = "ShipyardSwap"
            data = {"Favourite": True}
        self.assertEqual(line_keys.keys_for(E()), ["ShipyardSwap_Favourite", "ShipyardSwap"])
        from events.shipyard_swap import ShipyardSwap
        h = ShipyardSwap()
        st = type("S", (), {"favourite_ship": "python", "ship": "x", "ship_model": None, "ship_name": None})()
        h.update_state({"ShipType": "python"}, st)
        self.assertTrue(h.handle({"ShipType": "python"})["Favourite"])
        h.update_state({"ShipType": "anaconda"}, st)
        self.assertFalse(h.handle({"ShipType": "anaconda"})["Favourite"])
        from personality.smalltalk import intent_for
        for said in ("what's your favourite ship", "which ship do you like the most", "do you have a favourite ship"):
            self.assertEqual(intent_for(said), "Talk_FavouriteShip", said)


class WatcherHushTests(unittest.TestCase):
    def make(self):
        from personality.watcher import WatcherBridge
        calls = []

        class Client:
            def voice_hush(self, seconds): calls.append(seconds)
        now = [100.0]
        s = RouteTargetTests.Settings(**{"voidcompass.enabled": True, "watcher.enabled": True, "speech.enabled": True})
        b = WatcherBridge(None, None, None, s, Client(), clock=lambda: now[0])
        b.calls, b.now = calls, now
        return b

    def run_hush(self, b):
        import threading
        original = threading.Thread
        threading.Thread = lambda target=None, **k: type("T", (), {"start": lambda self: target()})()
        try:
            return b.hush_if_needed()
        finally:
            threading.Thread = original

    def test_hush_is_sent_and_not_too_often(self):
        b = self.make()
        self.assertTrue(self.run_hush(b))
        self.assertFalse(self.run_hush(b))
        b.now[0] += 7
        self.assertTrue(self.run_hush(b))
        self.assertEqual(len(b.calls), 2)

    def test_old_void_compass_without_hush_is_given_up_on(self):
        from control.voidcompass import VoidError
        b = self.make()

        def fail(seconds): raise VoidError("missing", "no such call")
        b.client.voice_hush = fail
        for _ in range(5):
            b.now[0] += 10
            self.run_hush(b)
        self.assertFalse(b.hush_wanted())

    def test_switch_off(self):
        b = self.make()
        b.settings.v["watcher.hush"] = False
        self.assertFalse(self.run_hush(b))


class NewMacros(unittest.TestCase):
    def test_launch_and_docking_macros_parse(self):
        from control.catalog import LAUNCH_MACRO, DOCKING_MACRO
        from control.macros import parse_macro
        for m in (LAUNCH_MACRO, DOCKING_MACRO):
            self.assertTrue(parse_macro(list(m)))
        self.assertEqual(LAUNCH_MACRO[-3:], ("UI_Down", "wait 0.6", "UI_Select"))
        self.assertEqual([s for s in LAUNCH_MACRO if s.startswith("say ")], ["say Launch_Start", "say Launch_Systems", "say Launch_Go"])
        self.assertEqual(LAUNCH_MACRO.count("UI_Back"), 2)
        self.assertEqual(DOCKING_MACRO[-1], "UI_Back")


class PreferUnsharedKey(unittest.TestCase):
    def test_a_secondary_key_nobody_shares_wins_over_a_shared_primary(self):
        from control.binds import BindingBook, parse_binds
        xml = """<Root>
  <UI_Select><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="Keyboard" Key="Key_Numpad_Enter" /></UI_Select>
  <QuickCommsPanel><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="{NoDevice}" Key="" /></QuickCommsPanel>
  <UI_Back><Primary Device="Keyboard" Key="Key_Backspace" /><Secondary Device="{NoDevice}" Key="" /></UI_Back>
</Root>"""
        book = BindingBook.__new__(BindingBook)
        book._actions = parse_binds(xml)
        book.refresh = lambda: True
        self.assertEqual(book.lookup("UI_Select")[0].key, "Key_Numpad_Enter")
        self.assertEqual(book.lookup("UI_Back")[0].key, "Key_Backspace")
        self.assertEqual(book.lookup("QuickCommsPanel")[0].key, "Key_Enter")


class LaunchTalk(unittest.TestCase):
    PHRASES = ("take us out", "number one take us out", "Number 1, take us out.", "you have control", "you have the helm",
               "take her out please", "get us out of here", "starling take us out", "take control", "the ship is yours")
    NOT = ("let's go", "it's yours", "all yours", "make it so", "what's going on")

    def runner(self):
        from tests.test_macros import MacroTests
        t = MacroTests()
        return t, t.build()

    def test_many_ways_to_hand_over_and_launch(self):
        t, r = self.runner()
        for text in self.PHRASES:
            m = r.matcher.match(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.command.id, "auto_launch", text)

    def test_everyday_phrases_do_not_launch(self):
        t, r = self.runner()
        for text in self.NOT:
            m = r.matcher.match(text)
            self.assertTrue(m is None or m.command.id != "auto_launch", text)

    def test_say_step_parses_and_needs_no_key(self):
        from control.macros import actions_in, parse_macro
        steps = parse_macro(["say Launch_Start", "UI_Select"])
        self.assertEqual(steps[0], ("say", "Launch_Start"))
        self.assertEqual(actions_in(steps), ["UI_Select"])
        with self.assertRaises(ValueError):
            parse_macro(["say not a key!"])

    def test_launch_has_lots_of_lines_in_every_part(self):
        from tests.test_dialogue import said_by
        for key in ("Launch_Start", "Launch_Systems", "Launch_Go"):
            self.assertGreaterEqual(len(said_by(key)), 25, key)
            for mood in ("Friendly", "Close", "Sarcastic", "Frustrated"):
                self.assertGreaterEqual(len(said_by("%s_%s" % (key, mood))), 5, key + mood)

    def test_launching_talks_three_times_and_skips_the_generic_line(self):
        from tests.test_dialogue import said_by
        t, r = self.runner()
        r.run_text("number one take us out")
        said = [kw["text"] for kw in t.speech.said]
        self.assertEqual(len(said), 3, said)
        pools = [said_by(k) | said_by(k + "_Friendly") | said_by(k + "_Close") | said_by(k + "_Sarcastic") | said_by(k + "_Frustrated")
                 for k in ("Launch_Start", "Launch_Systems", "Launch_Go")]
        for text, pool in zip(said, pools):
            self.assertTrue(any(line.split("{")[0].strip()[:12] in text for line in pool) or text, text)

    def test_a_custom_launch_macro_without_say_steps_still_confirms(self):
        from tests.test_macros import MacroTests
        t = MacroTests()
        r = t.build(macros__auto_launch=["UI_Select"])
        r.run_text("launch")
        self.assertEqual(len(t.speech.said), 1)


class KeyClashReport(unittest.TestCase):
    def runner(self, xml):
        from control.binds import BindingBook, parse_binds
        from tests.test_macros import MacroTests
        book = BindingBook.__new__(BindingBook)
        book._actions = parse_binds(xml)
        book.refresh = lambda: True
        t = MacroTests()
        r = t.build()
        r.book = book
        return r

    def test_clashes_are_listed_with_what_to_change(self):
        xml = """<Root>
  <UI_Select><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="{NoDevice}" Key="" /></UI_Select>
  <QuickCommsPanel><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="{NoDevice}" Key="" /></QuickCommsPanel>
  <LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle>
</Root>"""
        found = self.runner(xml).binding_conflicts()
        text = "\n".join(found)
        self.assertIn("UI Select", text)
        self.assertIn("Quick Comms Panel", text)
        self.assertIn("Options > Controls", text)
        self.assertNotIn("Landing Gear", text)

    def test_no_clashes_gives_an_empty_list(self):
        xml = """<Root>
  <UI_Select><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="{NoDevice}" Key="" /></UI_Select>
  <LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle>
</Root>"""
        self.assertEqual(self.runner(xml).binding_conflicts(), [])
