import unittest

from control.bio_voice import BioOverlayVoice
from journal.bio_predict import BioPredictor
from journal.game_state import GameState
from tests.test_bio_predict import fss, planet, run
from ui import bio_overlay as ov


class Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class Formatting(unittest.TestCase):
    def test_credits(self):
        self.assertEqual(ov.short_credits(4200000), "4.2M")
        self.assertEqual(ov.short_credits(19010800), "19M")
        self.assertEqual(ov.short_credits(850000), "850K")
        self.assertEqual(ov.short_credits(0), "?")

    def test_rows_and_flags(self):
        rows = [{"body": "A 1", "count": 2, "new": 5, "value": 4200000, "known": False, "kind": "icy"},
                {"body": "A 2", "count": 1, "new": 0, "value": 1500000, "known": True}]
        lines, more = ov.overlay_rows(rows)
        self.assertEqual(lines[0]["flags"], 2)                  # never more flags than signals
        self.assertEqual(lines[0]["value"], "~4.2M")            # a guess
        self.assertEqual(lines[1]["value"], "1.5M")             # scanned: no tilde
        self.assertEqual(lines[1]["flags"], 0)
        self.assertEqual(more, "")

    def test_more(self):
        rows = [{"body": "P%d" % i, "count": 1, "new": 0, "value": 1, "known": True} for i in range(11)]
        lines, more = ov.overlay_rows(rows)
        self.assertEqual((len(lines), more), (8, "and 3 more"))


class Placement(unittest.TestCase):
    def test_bottom_left_quarter_up(self):
        x, y = ov.placement(1920, 1080, 300, 200, 3, 25)
        self.assertEqual(x, 57)
        self.assertEqual(y, 1080 - 270 - 200)

    def test_stays_on_screen(self):
        x, y = ov.placement(1000, 800, 400, 300, 95, 95)
        self.assertLessEqual(x + 400, 1000)
        self.assertGreaterEqual(y, 0)


class When(unittest.TestCase):
    def test_shows_only_planets_with_life_and_forgets(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 2)])
        rows, test = ov.wanted(Settings(), state)
        self.assertEqual(len(rows), 1)
        self.assertFalse(test)
        self.assertEqual(rows[0]["count"], 2)
        self.assertGreater(rows[0]["value"], 0)
        state.bio.set_system("Elsewhere")
        self.assertEqual(ov.wanted(Settings(), state)[0], [])

    def test_switch_off_and_hidden(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1)])
        self.assertEqual(ov.wanted(Settings(**{"overlay.bio_enabled": False}), state)[0], [])
        state.bio.hidden = True
        self.assertEqual(ov.wanted(Settings(), state)[0], [])

    def test_test_mode(self):
        rows, test = ov.wanted(Settings(), GameState(), now=5.0, test_until=10.0)
        self.assertTrue(test)
        self.assertEqual(len(rows), 3)
        self.assertEqual(ov.wanted(Settings(), GameState(), now=11.0, test_until=10.0)[0], [])


class Voice(unittest.TestCase):
    def test_hide_and_show(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1)])
        voice = BioOverlayVoice(lambda: state)
        for text in ("hide the bio overlay", "Close the biology overlay.", "get rid of the exobiology box", "turn off the bio list"):
            state.bio.hidden = False
            self.assertEqual(voice.try_handle(text), "Biology overlay hidden.", text)
            self.assertTrue(state.bio.hidden)
        for text in ("show the bio overlay", "bring up the biology list please"):
            state.bio.hidden = True
            self.assertEqual(voice.try_handle(text), "Biology overlay shown.", text)
            self.assertFalse(state.bio.hidden)

    def test_ignores_everything_else(self):
        _, state = run([])
        voice = BioOverlayVoice(lambda: state)
        for text in ("hide the galaxy map", "show me the overlay", "plot a route to Colonia", "", "open the bio hatch"):
            self.assertIsNone(voice.try_handle(text), text)

    def test_hidden_clears_in_next_system(self):
        _, state = run([])
        state.bio.hidden = True
        state.bio.set_system("Elsewhere")
        self.assertFalse(state.bio.hidden)


if __name__ == "__main__":
    unittest.main()


class FakeCanvas:
    def __init__(self, *a, **k):
        self.items = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.items.append((name, args, kwargs))
        return call


class FakeWindow(FakeCanvas):
    def winfo_id(self):
        return 1


class FakeTk:
    Toplevel = FakeWindow
    Canvas = FakeCanvas


class FakeRoot:
    def __init__(self):
        self.jobs = []

    def after(self, ms, fn):
        self.jobs.append(fn)

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class DrawingTests(unittest.TestCase):
    """Runs the drawing code against a stand-in for tkinter (there is no screen here), to catch typing mistakes."""

    def setUp(self):
        import sys
        self._saved = sys.modules.get("tkinter")
        sys.modules["tkinter"] = FakeTk

    def tearDown(self):
        import sys
        if self._saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = self._saved

    def test_draw_show_and_hide(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 2)])
        root = FakeRoot()
        box = ov.BioOverlay(root, Settings(), lambda: state)
        box._update()
        names = [n for n, _, _ in box.canvas.items]
        self.assertIn("create_polygon", names)                 # a white flag
        self.assertIn("create_oval", names)                    # a planet
        self.assertEqual([n for n, _, _ in box.window.items if n == "deiconify"], ["deiconify"])
        before = len(box.canvas.items)
        box._update()                                          # nothing changed: no redraw
        self.assertEqual(len(box.canvas.items), before)
        state.bio.hidden = True
        box._update()
        self.assertIn("withdraw", [n for n, _, _ in box.window.items])

    def test_test_button(self):
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: GameState())
        box.show_test(5)
        box._update()
        self.assertIsNotNone(box.window)
        for dark in (True, False):
            for size in ("Small", "Large"):
                box._draw(*ov.overlay_rows(ov.TEST_ROWS), (3, 25, size, dark))


def saa(genera, name="Test A 1", body_id=5):
    return {"event": "SAASignalsFound", "BodyName": name, "BodyID": body_id, "SystemAddress": 1,
            "Signals": [{"Type_Localised": "Biological", "Count": len(genera)}], "Genuses": [{"Genus_Localised": g} for g in genera]}


def sample(stage, species, genus, body_id=5):
    return {"event": "ScanOrganic", "ScanType": stage, "Genus_Localised": genus, "Species_Localised": species,
            "Variant_Localised": species, "Body": body_id, "SystemAddress": 1}


class DetailedView(unittest.TestCase):
    def mapped(self, extra=()):
        entries = [planet("Test A 1", k=177, SystemAddress=1, WasFootfalled=True), fss("Test A 1", 2), saa(["Aleoida", "Tussock"])]
        return run(entries + list(extra))

    def test_view_appears_after_mapping(self):
        _, state = self.mapped()
        view = state.bio.focus_view()
        self.assertEqual([l["name"] for l in view["lives"]], ["Aleoida", "Tussock"])
        self.assertTrue(all(l["new"] and not l["done"] for l in view["lives"]))
        self.assertTrue(all(not l["exact"] for l in view["lives"]))

    def test_species_and_strike_through_and_codex_flag(self):
        _, state = self.mapped([sample("Log", "Aleoida Arcus", "Aleoida"), sample("Analyse", "Aleoida Arcus", "Aleoida")])
        lives = state.bio.focus_view()["lives"]
        self.assertEqual(lives[0]["name"], "Aleoida Arcus")
        self.assertTrue(lives[0]["done"])
        self.assertFalse(lives[0]["new"] and False)
        self.assertFalse(lives[1]["done"])
        lines = ov.overlay_focus(state.bio.focus_view())["lives"]
        self.assertTrue(lines[0]["done"])
        self.assertFalse(lines[0]["flag"])             # finished: no flag any more
        self.assertTrue(lines[1]["flag"])

    def test_codex_known_species_has_no_flag(self):
        _, state = self.mapped()
        state.bio.codex.add("Aleoida Arcus", state.bio.region)         # already in your codex before you sample it
        for e in (sample("Log", "Aleoida Arcus", "Aleoida"),):
            state.bio.note_organic(e)
        self.assertFalse(state.bio.focus_view()["lives"][0]["new"])

    def test_first_footfall_is_times_five(self):
        normal = self.mapped()[1].bio.focus_view()["lives"][0]["value"]
        entries = [planet("Test A 1", k=177, SystemAddress=1, WasFootfalled=False), fss("Test A 1", 2), saa(["Aleoida", "Tussock"])]
        first = run(entries)[1].bio.focus_view()["lives"][0]["value"]
        self.assertEqual(first, normal * 5)
        self.assertAlmostEqual(run(entries)[1].bio.rows()[0]["value"], 5 * self.mapped()[1].bio.rows()[0]["value"], delta=5)

    def test_target_rules(self):
        _, state = self.mapped()
        bio = state.bio
        bio.note_target(None)                 # never targeted it (yet): stays
        self.assertIsNotNone(bio.focus_view())
        bio.note_target(5)                    # target is the planet
        bio.note_target(5)
        self.assertIsNotNone(bio.focus_view())
        bio.note_target(7)                    # another body: back to the list
        self.assertIsNone(bio.focus_view())

    def test_untargeting_after_targeting_goes_back(self):
        _, state = self.mapped()
        state.bio.note_target(5)
        state.bio.note_target(None)
        self.assertIsNone(state.bio.focus_view())

    def test_new_system_clears_it(self):
        _, state = self.mapped()
        state.bio.set_system("Elsewhere")
        self.assertIsNone(state.bio.focus_view())

    def test_status_json_destination_reaches_the_overlay(self):
        from journal.status_reader import StatusReader
        from tests.helpers import make_processor
        processor, _bus, _heard = make_processor()
        processor.state.bio = self.mapped()[1].bio
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 1, "Destination": {"System": 1, "Body": 5, "Name": "Test A 1"}})
        reader.handle_status({"Flags": 1, "Destination": {"System": 1, "Body": 9, "Name": "Other"}})
        self.assertIsNone(processor.state.bio.focus_view())

    def test_wanted_focus_respects_switches_and_test_mode(self):
        _, state = self.mapped()
        self.assertIsNotNone(ov.wanted_focus(Settings(), state))
        self.assertIsNone(ov.wanted_focus(Settings(**{"overlay.bio_enabled": False}), state))
        state.bio.hidden = True
        self.assertIsNone(ov.wanted_focus(Settings(), state))
        self.assertIsNone(ov.wanted_focus(Settings(), GameState(), now=1.0, test_until=10.0))       # first half of the test: the list
        self.assertIsNotNone(ov.wanted_focus(Settings(), GameState(), now=7.0, test_until=10.0))    # second half: the planet view


class DetailedDrawing(DrawingTests):
    def test_draws_strike_and_flags_and_goes_back_to_list(self):
        _, state = DetailedView().mapped([sample("Log", "Aleoida Arcus", "Aleoida"), sample("Analyse", "Aleoida Arcus", "Aleoida")])
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: state)
        box._update()
        names = [n for n, _, _ in box.canvas.items]
        self.assertIn("create_line", names)                    # the line through the finished one
        self.assertIn("create_polygon", names)                 # a flag for the other
        before = len(box.canvas.items)
        box._update()
        self.assertEqual(len(box.canvas.items), before)        # unchanged: no redraw
        state.bio.note_target(99)
        box._update()                                          # back to the list
        self.assertGreater(len(box.canvas.items), 0)
        for dark in (True, False):
            for size in ("Small", "Large"):
                box._draw_focus(ov.overlay_focus(ov.TEST_FOCUS), (3, 25, size, dark))


class Billions(unittest.TestCase):
    def test_a_thousand_million_is_a_billion(self):
        from journal.exobiology import spoken_credits
        from memory.keeper import credits
        self.assertEqual(spoken_credits(1_000_000_000), "1 billion")
        self.assertEqual(spoken_credits(1_300_000_000), "1.3 billion")
        self.assertEqual(spoken_credits(999_000_000), "999 million")
        self.assertEqual(ov.short_credits(2_500_000_000), "2.5B")
        self.assertEqual(credits(3_000_000_000), "3 billion credits")


class LandingAndValue(unittest.TestCase):
    def mapped(self, extra=()):
        return DetailedView().mapped(extra)

    def test_value_does_not_collapse_after_the_first_sample(self):
        _, state = self.mapped()
        before = state.bio.rows()[0]["value"]
        _, after_state = self.mapped([sample("Log", "Aleoida Arcus", "Aleoida")])
        row = after_state.bio.rows()[0]
        self.assertGreater(row["value"], before * 0.3)           # the second life form is still counted, not forgotten
        self.assertFalse(row["known"])                           # one of two is still a guess
        self.assertEqual(row["new"], 2)                          # both still new to the codex

    def test_flags_drop_only_for_finished_forms(self):
        _, state = self.mapped([sample("Log", "Aleoida Arcus", "Aleoida"), sample("Analyse", "Aleoida Arcus", "Aleoida")])
        self.assertEqual(state.bio.rows()[0]["new"], 1)

    def test_planet_view_stays_while_landing_and_landed(self):
        _, state = self.mapped()
        bio = state.bio
        bio.note_target(5)                                     # targeted it
        bio.note_target(None, near="Test A 1")                 # the game drops the target as you come down
        self.assertIsNotNone(bio.focus_view())
        bio.note_target(None, hold=True)                       # gear down / landed / SRV / on foot
        bio.note_target(9, hold=True)
        self.assertIsNotNone(bio.focus_view())
        bio.note_target(None, near="Test A 1")                 # took off but still in orbit: stays
        self.assertIsNotNone(bio.focus_view())
        bio.note_target(5, near="")                            # left orbit (the game no longer names the planet): back to the list
        self.assertIsNone(bio.focus_view())

    def test_status_flags_reach_it(self):
        from journal.status_reader import StatusReader
        from tests.helpers import make_processor
        processor, _bus, _heard = make_processor()
        processor.state.bio = self.mapped()[1].bio
        reader = StatusReader(None, processor, min_gap_seconds={})
        reader.handle_status({"Flags": 1, "Destination": {"Body": 5}})
        reader.handle_status({"Flags": 1 | 4})                 # landing gear down, target gone
        self.assertIsNotNone(processor.state.bio.focus_view())


class RegionColours(unittest.TestCase):
    SOL = (0.0, 0.0, 0.0)               # Inner Orion Spur
    COLONIA = (-9530.5, -910.3, 19808.1)

    def test_codex_knows_where(self):
        from journal.bio_predict import BioCodex
        c = BioCodex()
        self.assertEqual(c.where("Aleoida Arcus", "Inner Orion Spur"), "never")
        c.add("Aleoida Arcus", "Inner Orion Spur")
        self.assertEqual(c.where("Aleoida Arcus", "Inner Orion Spur"), "here")
        self.assertEqual(c.where("Aleoida Arcus", "Odin's Hold"), "elsewhere")
        c.add("Old One")                                    # old data without regions: never called "elsewhere"
        self.assertEqual(c.where("Old One", "Odin's Hold"), "here")

    def test_codex_entry_names_its_region_and_it_is_saved(self):
        import tempfile, pathlib
        from journal.bio_predict import BioCodex
        p = pathlib.Path(tempfile.mkdtemp()) / "c.json"
        c = BioCodex(p)
        c._from_entry({"event": "CodexEntry", "Name_Localised": "Aleoida Arcus - Red", "Region_Localised": "Odin's Hold"}, {"aleoida arcus"})
        again = BioCodex(p)
        self.assertEqual(again.where("Aleoida Arcus", "Odin's Hold"), "here")
        self.assertEqual(again.where("Aleoida Arcus", "Inner Orion Spur"), "elsewhere")

    def test_history_scan_reads_regions_once(self):
        import tempfile, pathlib, json
        from journal.bio_predict import BioCodex
        folder = pathlib.Path(tempfile.mkdtemp())
        lines = [{"event": "FSDJump", "StarSystem": "S", "StarPos": list(self.COLONIA)},
                 {"event": "ScanOrganic", "ScanType": "Analyse", "Species_Localised": "Aleoida Arcus"}]
        (folder / "Journal.2026-01-01T000000.01.log").write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
        c = BioCodex()
        c.scan_history(folder)
        self.assertTrue(c.regions_done)
        from navigation.regions import region_of
        far = region_of(self.COLONIA)[1]
        self.assertEqual(c.where("Aleoida Arcus", far), "here")
        self.assertEqual(c.where("Aleoida Arcus", "Inner Orion Spur"), "elsewhere")

    def test_overlay_colours(self):
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 2), saa(["Aleoida", "Tussock"])])
        bio = state.bio
        bio.set_position(self.SOL)
        self.assertEqual(bio.region, "Inner Orion Spur")
        bio.codex.add("Tussock Albata", "Odin's Hold")
        for r in bio.rules:
            if r["g"] == "Tussock":
                bio.codex.add(r["n"], "Odin's Hold")        # every Tussock found, but in another region
        lives = bio.focus_view()["lives"]
        self.assertEqual([l["status"] for l in lives], ["never", "elsewhere"])
        lines = ov.overlay_focus(bio.focus_view())["lives"]
        self.assertEqual([l["flag"] for l in lines], [True, True])
        row = ov.overlay_rows(bio.rows())[0][0]
        self.assertEqual(row["flag_colors"], [ov.YELLOW, ov.BLUE])
        self.assertEqual(row["tone"], "never")
        for r in bio.rules:
            if r["g"] == "Tussock":
                bio.codex.add(r["n"], "Inner Orion Spur")   # now found here too: orange, no flag
        lines = ov.overlay_focus(bio.focus_view())["lives"]
        self.assertEqual([l["status"] for l in lines], ["never", "here"])
        self.assertFalse(lines[1]["flag"])

    def test_finished_form_is_orange_and_flagless(self):
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"]),
                        sample("Log", "Aleoida Arcus", "Aleoida"), sample("Analyse", "Aleoida Arcus", "Aleoida")])
        line = ov.overlay_focus(state.bio.focus_view())["lives"][0]
        self.assertEqual((line["status"], line["flag"], line["done"]), ("here", False, True))

    def test_position_from_events(self):
        got, state = run([{"event": "FSDJump", "StarSystem": "Test", "StarPos": list(self.SOL), "SystemAddress": 1}])
        self.assertEqual(state.bio.region, "Inner Orion Spur")


class Ranges(unittest.TestCase):
    def test_spoken_range(self):
        from journal.exobiology import spoken_range
        self.assertEqual(spoken_range(1_000_000, 19_000_000), "1 to 19 million")
        self.assertEqual(spoken_range(800_000, 19_000_000), "800 thousand to 19 million")
        self.assertEqual(spoken_range(4_000_000, 4_200_000), "4.1 million")          # close together: one number
        self.assertEqual(spoken_range(900_000_000, 1_500_000_000), "900 million to 1.5 billion")

    def test_short_range(self):
        self.assertEqual(ov.short_range(1_000_000, 19_000_000), "~1-19M")
        self.assertEqual(ov.short_range(800_000, 19_000_000), "~800K-19M")
        self.assertEqual(ov.short_range(4_000_000, 4_100_000), "~4M")
        self.assertEqual(ov.short_range(0, 0), "~?")

    def test_guess_is_a_range_from_the_cheapest_to_the_dearest_species(self):
        rules = [{"n": "Bacterium Aurasus", "g": "Bacterium", "p": ["rocky"], "a": ["carbondioxide"]},
                 {"n": "Stratum Tectonicas", "g": "Stratum", "p": ["rocky"], "a": ["carbondioxide"]}]
        from journal.bio_predict import BioPredictor, BioCodex
        from journal.exobiology import ExobiologyTracker
        t = ExobiologyTracker(None)
        t.seed = {"bacterium aurasus": 1_000_000, "stratum tectonicas": 19_000_000}
        p = BioPredictor(t, BioCodex(), None, rules)
        p.set_system("Test")
        p.note_scan(planet("Test A 1", k=177, SystemAddress=1))
        body = p._body("Test A 1", 1)
        body.candidates = p.candidates_for("Test A 1")
        low, expected, high = p.estimate(body)
        self.assertEqual((low, high), (1_000_000, 19_000_000))
        events = p._guess_events(body)
        self.assertEqual(dict(events)["BioGuess"]["Worth"], "1 to 19 million")
        row = p.rows()[0]
        self.assertEqual(ov.overlay_rows([row])[0][0]["value"], "~1-19M")

    def test_planet_view_shows_a_range_until_identified_then_the_price(self):
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"])])
        line = ov.overlay_focus(state.bio.focus_view())["lives"][0]
        self.assertTrue(line["value"].startswith("~"))
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"]), sample("Log", "Aleoida Arcus", "Aleoida")])
        self.assertFalse(ov.overlay_focus(state.bio.focus_view())["lives"][0]["value"].startswith("~"))

    def test_never_found_stays_yellow_while_you_sample_it(self):
        base = [planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"])]
        for extra in ([sample("Log", "Aleoida Arcus", "Aleoida")],
                      [{"event": "CodexEntry", "Name_Localised": "Aleoida Arcus - Red", "Region_Localised": "Inner Orion Spur"}, sample("Log", "Aleoida Arcus", "Aleoida")],
                      [sample("Log", "Aleoida Arcus", "Aleoida"), sample("Vital", "Aleoida Arcus", "Aleoida")]):
            _, state = run(base + extra)
            state.bio.set_position((0.0, 0.0, 0.0))
            line = ov.overlay_focus(state.bio.focus_view())["lives"][0]
            self.assertEqual(line["tone"], "never", extra)       # the colour does not flip halfway through the three samples

    def test_finished_form_turns_orange_whatever_colour_it_had(self):
        base = [planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"])]
        _, state = run(base + [sample("Log", "Aleoida Arcus", "Aleoida"), sample("Analyse", "Aleoida Arcus", "Aleoida")])
        state.bio.set_position((0.0, 0.0, 0.0))
        line = ov.overlay_focus(state.bio.focus_view())["lives"][0]
        self.assertEqual((line["tone"], line["flag"], line["done"]), ("here", False, True))
        self.assertEqual(ov.TONES[line["tone"]], ov.ORANGE)

    def test_found_in_another_region_is_blue_until_you_finish_it_then_orange(self):
        """She said: scanned it three times and it stayed blue until she scanned it on another planet."""
        _, state = run([planet("Test A 1", k=177, SystemAddress=1, body_id=5), fss("Test A 1", 1, body_id=5), saa(["Aleoida"], body_id=5)])
        bio = state.bio
        bio.set_position((0.0, 0.0, 0.0))                                   # Inner Orion Spur
        bio.codex.add("Aleoida Arcus", "Odin's Hold")                       # found before, but in another region
        bio.note_organic(sample("Log", "Aleoida Arcus", "Aleoida"))
        self.assertEqual(bio.focus_view()["lives"][0]["tone"], "elsewhere")  # still blue while sampling
        bio.note_organic(sample("Analyse", "Aleoida Arcus", "Aleoida"))
        line = bio.focus_view()["lives"][0]
        self.assertEqual((line["tone"], line["status"], line["done"]), ("here", "here", True))
        # the very next planet in the system that has the same species: no longer new, so orange with no flag
        bio.note_scan(planet("Test A 2", k=177, SystemAddress=1, body_id=6))
        bio.note_fss(fss("Test A 2", 1, body_id=6))
        bio.note_saa(saa(["Aleoida"], name="Test A 2", body_id=6))
        bio.note_organic(dict(sample("Log", "Aleoida Arcus", "Aleoida"), Body=6))
        bio.focus = "Test A 2"
        other = bio.focus_view()["lives"][0]
        self.assertEqual((other["tone"], other["new"]), ("here", False))


class ManyFlags(DrawingTests):
    ROW = {"body": "A 3", "count": 12, "value": 90_000_000, "low": 45_700_000, "high": 175_300_000, "new": 12,
           "flags": ["never"] * 5 + ["elsewhere"] * 7, "known": False, "kind": "icy", "species": [], "genera": []}

    def test_twelve_signals_and_long_range_go_on_two_lines(self):
        line = ov.overlay_rows([self.ROW])[0][0]
        self.assertEqual(line["flags"], 12)
        self.assertTrue(line["two_line"])
        self.assertEqual(line["value"], "~45.7-175.3M")
        few = dict(self.ROW, count=3, flags=["never", "elsewhere"], new=2)
        self.assertFalse(ov.overlay_rows([few])[0][0]["two_line"])

    def test_draws_and_fits(self):
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: GameState())
        for size in ("Small", "Medium", "Large"):
            if box.canvas is not None:
                box.canvas.items.clear()           # the stand-in canvas does not clear itself
            box._draw(*ov.overlay_rows([self.ROW, dict(self.ROW, count=2, flags=["never"], new=1)]), (3, 25, size, False))
            flags = [a for n, a, _ in box.canvas.items if n == "create_polygon"]
            self.assertEqual(len(flags), 13)
            width = int(ov.SIZES[size] * 23)
            for args in flags:
                self.assertLess(max(args[0::2]), width - 10)          # every flag stays inside the box


class GameQuits(DrawingTests):
    def test_shutdown_hides_everything_and_forgets(self):
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"])])
        self.assertIsNotNone(ov.wanted_focus(Settings(), state))
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: state)
        box._update()
        self.assertIsNotNone(box.window)
        got, state2 = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1), saa(["Aleoida"]), {"event": "Shutdown"}])
        self.assertTrue(state2.game_quit)
        self.assertEqual(ov.wanted(Settings(), state2)[0], [])
        self.assertIsNone(ov.wanted_focus(Settings(), state2))
        self.assertEqual(state2.bio.rows(), [])                 # her memory of the system is gone too
        box2 = ov.BioOverlay(FakeRoot(), Settings(), lambda: state2)
        box2._update()
        self.assertIsNone(box2.window)                          # never even drawn

    def test_loading_in_again_clears_it(self):
        got, state = run([{"event": "Shutdown"}, {"event": "LoadGame", "Commander": "X"}])
        self.assertFalse(state.game_quit)
        got, state = run([{"event": "Shutdown"}, {"event": "FSDJump", "StarSystem": "Test", "StarPos": [0, 0, 0]}])
        self.assertFalse(state.game_quit)

    def test_shown_overlay_is_withdrawn_on_shutdown(self):
        _, state = run([planet("Test A 1", k=177, SystemAddress=1), fss("Test A 1", 1)])
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: state)
        box._update()
        state.game_quit = True
        box._update()
        self.assertIn("withdraw", [n for n, _, _ in box.window.items])
