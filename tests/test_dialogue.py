import json
import random
import tempfile
import unittest
from pathlib import Path

from core import paths
from core.event_bus import Event
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.speaker import EventSpeaker
from personality import line_keys


def real_dialogue():
    return DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"],
                           rng=random.Random(1)).load()


def said_by(key):
    """Every text she might use for a dialogue key (lines now come in several wordings)."""
    return {line.text for line in real_dialogue().lines[key]}


class RealVoicePackTests(unittest.TestCase):
    def test_the_pack_has_no_mp3_recordings(self):
        folder = paths.VOICEPACKS_DIR / "default"
        self.assertEqual(list(folder.rglob("audio/*.mp3")), [])
        d = real_dialogue()
        self.assertEqual([l for ls in d.lines.values() for l in ls if l.audio], [])
        self.assertEqual(d.missing_audio(), [])

    def test_every_line_is_plain_speakable_text(self):
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key, lines in real_dialogue().lines.items():
            for line in lines:
                self.assertTrue(line.text.strip(), key)
                for word in banned:
                    self.assertNotIn(word, line.text.lower(), "%s: %s" % (key, line.text))

    def test_no_line_is_repeated_inside_a_key(self):
        for key, lines in real_dialogue().lines.items():
            texts = [l.text for l in lines]
            self.assertEqual(len(texts), len(set(texts)), key)

    def test_main_safety_events_have_lines(self):
        d = real_dialogue()
        for key in ("HullDamage", "HullDamage_Critical", "ShieldsDown", "UnderAttack", "Interdicted",
                    "InterdictionInProgress", "Died", "Overheating", "LowFuel", "MissionFailed"):
            self.assertIsNotNone(d.pick(key, "Friendly"), key)

    def test_low_fuel_lines_carry_the_percentage(self):
        for line in real_dialogue().lines["LowFuel"]:
            self.assertIn("{fuel_percent}", line.text)

    def test_mature_lines_are_hidden_unless_allowed(self):
        d = real_dialogue()
        self.assertTrue(all(not l.mature for l in d.pool("UnderAttack", "Sarcastic")))
        self.assertTrue(any(l.mature for l in d.pool("UnderAttack", "Sarcastic", allow_mature=True)))

    def test_mood_variation_adds_lines(self):
        d = real_dialogue()
        self.assertGreater(len(d.pool("Bounty", "Friendly")), len(d.pool("Bounty", "")))

    def test_same_line_is_not_repeated_straight_away(self):
        d = real_dialogue()
        picks = [d.pick("Bounty", "Friendly").text for _ in range(3)]
        self.assertEqual(len(set(picks)), 3)


class SmallDialogueTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.pack = Path(self.folder.name)
        (self.pack / "audio").mkdir()
        (self.pack / "audio" / "a.mp3").write_bytes(b"x")
        (self.pack / "pack.json").write_text(json.dumps({"name": "T"}))
        (self.pack / "dialogue.json").write_text(json.dumps({
            "Docked": [{"text": "Recorded.", "audio": "a.mp3"}, "Just text."],
            "Gone": [{"text": "Missing file.", "audio": "nope.mp3"}],
        }))

    def tearDown(self):
        self.folder.cleanup()

    def test_recorded_lines_beat_text_only_lines(self):
        d = DialogueManager(self.pack).load()
        self.assertEqual({d.pick("Docked").text for _ in range(10)}, {"Recorded."})

    def test_text_only_lines_are_used_when_recording_preference_is_off(self):
        d = DialogueManager(self.pack, rng=random.Random(3)).load()
        texts = {d.pick("Docked", prefer_recorded=False).text for _ in range(20)}
        self.assertEqual(texts, {"Recorded.", "Just text."})

    def test_line_with_missing_mp3_still_works_as_text(self):
        d = DialogueManager(self.pack).load()
        line = d.pick("Gone")
        self.assertIsNone(d.audio_path(line))
        self.assertEqual(d.missing_audio(), [("Gone", "nope.mp3")])

    def test_unknown_key_gives_none(self):
        self.assertIsNone(DialogueManager(self.pack).load().pick("Nothing"))

    def test_missing_pack_folder_is_not_a_crash(self):
        with self.assertLogs("starling.dialogue", level="WARNING"):
            d = DialogueManager(self.pack / "nope").load()
        self.assertEqual(d.lines, {})


class FakeSpeech:
    def __init__(self):
        self.said = []

    def say(self, **kwargs):
        self.said.append(kwargs)
        return True


class SpeakerTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
        self.speech = FakeSpeech()
        self.now = [0.0]
        self.rules = {"default_cooldown_seconds": 2.5, "cooldown_seconds": {"FuelScoopStarted": 100}, "max_age_seconds": {}}
        self.speaker = EventSpeaker(None, self.speech, real_dialogue(), self.settings, self.rules,
                                    clock=lambda: self.now[0])

    def event(self, name, priority="normal", **data):
        return Event(name=name, data=data, priority=priority)

    def test_event_is_spoken_as_text_with_its_priority(self):
        self.speaker.on_event(self.event("Docked"))
        said = self.speech.said[0]
        self.assertEqual(said["priority"], "normal")
        self.assertIsNone(said["audio_path"])
        self.assertTrue(said["text"])

    def test_cooldown_stops_repeats(self):
        self.speaker.on_event(self.event("FuelScoopStarted", "low"))
        self.now[0] = 50
        self.speaker.on_event(self.event("FuelScoopStarted", "low"))
        self.assertEqual(len(self.speech.said), 1)
        self.now[0] = 150
        self.speaker.on_event(self.event("FuelScoopStarted", "low"))
        self.assertEqual(len(self.speech.said), 2)

    def test_critical_event_without_any_line_speaks_its_summary(self):
        self.speaker.on_event(self.event("InterdictionInProgress", "critical", summary="Interdiction in progress"))
        # this one has a recording, so check one that has none:
        self.speaker.on_event(self.event("VeryHotWarning", "critical", summary="Dangerously hot"))
        self.speaker.on_event(self.event("SomethingNew", "critical", summary="Something new happened"))
        self.assertEqual(self.speech.said[-1]["text"], "Something new happened")
        self.assertEqual(self.speech.said[-1]["priority"], "critical")

    def test_ordinary_event_without_a_line_stays_quiet(self):
        self.speaker.on_event(self.event("LightsOn", "low", summary="Lights on"))
        self.assertEqual(self.speech.said, [])

    def test_low_fuel_fills_in_the_percentage(self):
        self.speaker.on_event(self.event("LowFuel", "critical", fuel_percent=20, summary="Fuel is low"))
        said = self.speech.said[0]
        self.assertIn("20 percent", said["text"])
        self.assertNotIn("{", said["text"])

    def test_low_fuel_without_percentage_uses_the_summary(self):
        self.speaker.on_event(self.event("LowFuel", "critical", summary="Fuel is low"))
        self.assertEqual(self.speech.said[0]["text"], "Fuel is low")

    def test_hull_damage_picks_the_critical_lines_when_low(self):
        keys = line_keys.keys_for(self.event("HullDamage", Percent=20))
        self.assertEqual(keys, ["HullDamage_Critical", "HullDamage"])
        self.assertEqual(line_keys.keys_for(self.event("HullDamage", Percent=80)), ["HullDamage"])

    def test_shield_state_uses_up_and_down_keys(self):
        self.assertEqual(line_keys.keys_for(self.event("ShieldState", ShieldsUp=False)), ["ShieldsDown"])
        self.assertEqual(line_keys.keys_for(self.event("ShieldState", ShieldsUp=True)), ["ShieldsUp"])

    def test_shields_up_has_a_text_line_so_it_is_never_silent(self):
        self.speaker.on_event(self.event("ShieldState", "critical", ShieldsUp=True, summary="Shields are back up"))
        self.assertIn(self.speech.said[0]["text"], said_by("ShieldsUp"))

    # ---- the fixes ----
    def test_hyperspace_start_jump_names_the_system_and_has_no_countdown(self):
        for i in range(30):
            self.now[0] = i * 100
            self.speaker.on_event(self.event("StartJump", JumpType="Hyperspace", StarSystem="Colonia", summary="x"))
        self.assertTrue(self.speech.said)
        for said in self.speech.said:
            self.assertIn("Colonia", said["text"])
            for word in ("Three", "Two", "One.", "Four"):
                self.assertNotIn(word, said["text"])

    def test_no_line_anywhere_counts_down_to_engage(self):
        import json
        from core import paths
        for name in ("dialogue.json", "personality.json", "commands.json"):
            path = paths.VOICEPACKS_DIR / "default" / name
            if path.exists():
                self.assertNotIn("Four.||Three", path.read_text(encoding="utf-8"))

    def test_ordinary_planets_and_stars_are_not_announced(self):
        for data in ({"PlanetClass": "High metal content body"}, {"StarType": "G"}, {"PlanetClass": "Icy body"},
                     {"BodyName": "Belt Cluster 1"}):
            self.now[0] += 100
            self.speaker.on_event(self.event("Scan", "low", summary="Scanned x", **data))
        self.assertEqual(self.speech.said, [])

    def test_interesting_bodies_are_announced_and_audible(self):
        cases = ((dict(PlanetClass="Earthlike body"), "Scan_EarthLike"),
                 (dict(PlanetClass="Water world"), "Scan_WaterWorld"),
                 (dict(PlanetClass="Ammonia world"), "Scan_AmmoniaWorld"),
                 (dict(PlanetClass="Gas giant with water based life"), "Scan_GreenGasGiant"),
                 (dict(PlanetClass="Gas giant with ammonia based life"), "Scan_GreenGasGiant"),
                 (dict(PlanetClass="Rocky body", TerraformState="Terraformable"), "Scan_Terraformable"),
                 (dict(StarType="N"), "Scan_NeutronStar"),
                 (dict(StarType="H"), "Scan_BlackHole"))
        for data, key in cases:
            self.now[0] += 100
            self.speaker.on_event(self.event("Scan", "low", summary="Scanned x", **data))
            self.assertIn(self.speech.said[-1]["text"], said_by(key), data)
            self.assertEqual(self.speech.said[-1]["priority"], "normal")
        self.assertEqual(len(self.speech.said), len(cases))

    def test_a_plain_gas_giant_is_not_a_green_one(self):
        for cls in ("Sudarsky class I gas giant", "Sudarsky class II gas giant", "Helium rich gas giant"):
            self.now[0] += 100
            self.speaker.on_event(self.event("Scan", "low", summary="x", PlanetClass=cls))
        self.assertEqual(self.speech.said, [])

    def test_galaxy_and_system_map_open_and_close_are_spoken(self):
        self.settings.set("personality.mood", "")
        cases = (("GalaxyMapOpened", {}, "GalaxyMapOpened"), ("SystemMapOpened", {}, "SystemMapOpened"),
                 ("ScreenClosed", {"screen": "galaxy map"}, "GalaxyMapClosed"),
                 ("ScreenClosed", {"screen": "system map"}, "SystemMapClosed"))
        for name, data, key in cases:
            self.now[0] += 100
            self.speaker.on_event(self.event(name, "normal", summary="x", **data))
            self.assertIn(self.speech.said[-1]["text"], said_by(key), name)
        self.assertEqual(len(self.speech.said), 4)

    def test_closing_other_screens_stays_quiet(self):
        for screen in ("codex", "right-hand panel", "system scanner"):
            self.now[0] += 100
            self.speaker.on_event(self.event("ScreenClosed", "normal", summary="x", screen=screen))
        self.assertEqual(self.speech.said, [])

    def test_map_calls_are_not_dropped_when_busy(self):
        from core.settings import load_event_config
        config = load_event_config()
        for name in ("GalaxyMapOpened", "SystemMapOpened", "ScreenClosed"):
            self.assertEqual(config[name]["priority"], "normal", name)

    def test_supercruise_start_jump_is_silent(self):
        self.speaker.on_event(self.event("StartJump", JumpType="Supercruise", summary="x"))
        self.assertEqual(self.speech.said, [])

    def test_charging_says_frameshift_drive_charging(self):
        self.settings.set("personality.mood", "")
        self.speaker.on_event(self.event("FsdCharging", summary="x"))
        self.assertIn(self.speech.said[0]["text"], said_by("FsdCharging"))

    def test_arriving_in_a_system_never_plays_engine_engaged(self):
        for i in range(30):
            self.now[0] = i * 100
            self.speaker.on_event(self.event("FSDJump", StarSystem="Sol", summary="x"))
        for said in self.speech.said:
            self.assertIsNone(said["audio_path"])
            self.assertNotIn("engage", said["text"].lower())
        self.assertTrue(self.speech.said)

    def test_fuel_scoop_calls_say_the_right_things(self):
        for name in ("FuelScoopStarted", "FuelScoopComplete", "FuelScoopDisengaged"):
            self.now[0] += 1000
            self.speaker.on_event(self.event(name, "normal", summary="x"))
            self.assertIn(self.speech.said[-1]["text"], said_by(name), name)

    def test_the_repeating_journal_fuel_scoop_event_is_silent(self):
        self.speaker.on_event(self.event("FuelScoop", "low", Scooped=1.0, summary="Scooped"))
        self.assertEqual(self.speech.said, [])

    def test_boarding_the_ship_says_docking_complete(self):
        self.speaker.on_event(self.event("VehicleChanged", vehicle="main ship", previous="SRV", summary="x"))
        self.assertIn(self.speech.said[0]["text"], ("Docking complete.", "Welcome back aboard."))

    def test_going_on_foot_uses_text_until_recorded(self):
        self.speaker.on_event(self.event("VehicleChanged", vehicle="on foot", previous="SRV", summary="x"))
        self.assertTrue(self.speech.said[0]["text"])

    def test_entering_another_vehicle_is_silent(self):
        self.speaker.on_event(self.event("VehicleChanged", vehicle="other vehicle", previous="main ship", summary="x"))
        self.assertEqual(self.speech.said, [])

    def test_exobiology_samples_say_the_species(self):
        self.speaker.on_event(self.event("ScanOrganic", ScanType="Log", Species_Localised="Aleoida Arcus", summary="x"))
        said = self.speech.said[0]
        self.assertIn("Aleoida Arcus", said["text"])
        self.assertNotIn("{", said["text"])

    def test_exobiology_analysis_complete(self):
        self.settings.set("personality.mood", "")
        self.speaker.on_event(self.event("ScanOrganic", ScanType="Analyse", Species_Localised="Bacterium", summary="x"))
        self.assertIn("Analysis complete", self.speech.said[0]["text"])

    def test_biological_signals_use_their_own_lines(self):
        self.speaker.on_event(self.event("SAASignalsFound", Biological=3, summary="x"))
        self.assertIn(self.speech.said[0]["text"], said_by("SAASignalsFound_Biological"))

    def test_planet_without_life_stays_quiet(self):
        self.speaker.on_event(self.event("SAASignalsFound", Biological=0, Geological=2, summary="x"))
        self.assertEqual(self.speech.said, [])

    def test_speech_can_be_switched_off(self):
        self.settings.set("speech.enabled", False)
        self.speaker.on_event(self.event("Docked"))
        self.assertEqual(self.speech.said, [])

    def test_app_and_speech_events_are_ignored(self):
        for name in ("app.started", "journal.file_changed", "speech.started"):
            self.speaker.on_event(self.event(name, "critical", summary="x"))
        self.assertEqual(self.speech.said, [])

    def test_mature_lines_never_chosen_by_default(self):
        for i in range(60):
            self.now[0] = i * 100
            self.speaker.on_event(self.event("UnderAttack", "critical", summary="Under attack"))
        mature = {l.text for l in real_dialogue().lines["UnderAttack_Sarcastic"] if l.mature}
        used = {s["text"] for s in self.speech.said}
        self.assertEqual(used & mature, set())


if __name__ == "__main__":
    unittest.main()


class ExobiologySpeechTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(Path(tempfile.gettempdir()) / "nope_exo.json").load()
        self.speech = FakeSpeech()
        rules = {"default_cooldown_seconds": 0, "cooldown_seconds": {}, "max_age_seconds": {}}
        self.speaker = EventSpeaker(None, self.speech, real_dialogue(), self.settings, rules)

    def say(self, **data):
        self.speaker.on_event(Event(name="ScanOrganic", data=dict(Species_Localised="Bacterium Informem", summary="x", **data),
                                    priority="normal"))
        return self.speech.said[-1]["text"]

    def test_first_scan_tells_the_value(self):
        text = self.say(ScanType="Log", SampleNumber=1, ValueKnown=True, worth="8.4 million", distance="500")
        self.assertIn("8.4 million", text)

    def test_first_scan_with_unknown_price_says_so(self):
        text = self.say(ScanType="Log", SampleNumber=1, ValueKnown=False, distance="500")
        self.assertNotIn("million", text)
        self.assertNotIn("{", text)

    def test_top_ten_species_use_the_excited_lines(self):
        text = self.say(ScanType="Log", SampleNumber=1, ValueKnown=True, Top10=True, worth="30 million",
                        distance="500")
        self.assertIn("30 million", text)
        self.assertIn(text.replace("Bacterium Informem", "{Species_Localised}").replace("30 million", "{worth}")
                      .replace("500", "{distance}"),
                      said_by("ScanOrganic_LogTop10") | said_by("ScanOrganic_LogTop10_Friendly")
                      | said_by("ScanOrganic_LogTop10_Close") | said_by("ScanOrganic_LogTop10_Sarcastic"))

    def test_second_sample_can_describe_the_species(self):
        text = self.say(ScanType="Sample", SampleNumber=2, About="A glowing, soil-dwelling thing.")
        self.assertIn("A glowing, soil-dwelling thing.", text)

    def test_third_sample_wording(self):
        text = self.say(ScanType="Sample", SampleNumber=3)
        self.assertIn(text.replace("Bacterium Informem", "{Species_Localised}"), said_by("ScanOrganic_Third"))

    def test_second_sample_wording(self):
        text = self.say(ScanType="Sample", SampleNumber=2)
        self.assertIn(text.replace("Bacterium Informem", "{Species_Localised}"), said_by("ScanOrganic_Sample"))

    def test_finished_species_tells_worth_then_total(self):
        text = self.say(ScanType="Analyse", Complete=True, ValueKnown=True, FirstFootfall=False,
                        worth="8.4 million", carried="25 million")
        parts = text.split("||")
        self.assertEqual(len(parts), 2)
        self.assertIn("Bacterium Informem", parts[0])
        self.assertNotIn("8.4 million", text)  # the value is now told on the first scan
        self.assertIn("25 million", parts[1])

    def test_first_footfall_is_mentioned(self):
        text = self.say(ScanType="Analyse", Complete=True, ValueKnown=True, FirstFootfall=True,
                        worth="42 million", carried="42 million")
        self.assertIn("footfall", text.lower())
        self.assertIn("42 million", text)

    def test_unknown_price_is_admitted_not_invented(self):
        text = self.say(ScanType="Analyse", Complete=True, ValueKnown=False)
        self.assertNotIn("million", text)
        self.assertIn("Bacterium Informem", text)

    def test_sale_says_the_amount(self):
        self.speaker.on_event(Event(name="SellOrganicData", data={"TotalValue": 40000000, "worth": "40 million",
                                                                  "summary": "x"}, priority="normal"))
        self.assertIn("40 million", self.speech.said[-1]["text"])
        self.speaker.on_event(Event(name="SellOrganicData", data={"TotalValue": 0, "worth": "0", "summary": "x"},
                                    priority="normal"))
        self.assertNotIn("0 credits", self.speech.said[-1]["text"])


class DistanceSpeechTests(ExobiologySpeechTests):
    def test_first_sample_tells_the_distance(self):
        text = self.say(ScanType="Log", SampleNumber=1, distance="500")
        self.assertIn("500 metres", text)
        self.assertIn("Bacterium Informem", text)
        self.assertEqual(len(text.split("||")), 3)  # species, value, distance

    def test_first_sample_without_a_known_distance_is_still_announced(self):
        text = self.say(ScanType="Log", SampleNumber=1)
        self.assertIn("Bacterium Informem", text)
        self.assertNotIn("metres", text)
