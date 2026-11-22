import json
import tempfile
from pathlib import Path

from PIL import Image

import random
import unittest

import numpy as np

from ui import hologram as h
from ui.hologram_window import HologramFeed
from ui.window_voice import WindowVoice, which


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def make(height=225):
    clock = Clock()
    return h.Hologram(h.Assets(height), random.Random(1), clock), clock


class Placement(unittest.TestCase):
    def test_size_scales_with_screen(self):
        self.assertEqual(h.height_for(1080, 100), 225)
        self.assertEqual(h.height_for(2160, 100), 450)
        self.assertEqual(h.height_for(1080, 150), 338)
        self.assertEqual(h.height_for(1080, 5000), h.height_for(1080, 200))

    def test_position_round_trip(self):
        x, y = h.window_position(1920, 1080, 151, 263, 6.5, 24)
        left, bottom = h.percents_from_position(1920, 1080, 151, 263, x, y)
        self.assertAlmostEqual(left, 6.5, delta=0.1)
        self.assertAlmostEqual(bottom, 24, delta=0.2)

    def test_stays_on_screen(self):
        x, y = h.window_position(1920, 1080, 151, 263, 500, 500)
        self.assertTrue(0 <= x <= 1920 - 151 and 0 <= y <= 1080 - 263)


class Mouth(unittest.TestCase):
    def test_track_uses_vowels_and_pauses(self):
        track = h.build_track("Hello, Ben.")
        self.assertTrue(h.track_length(track) > 0.3)
        names = {h.shape_at(track, t / 20.0) for t in range(0, int(h.track_length(track) * 20) + 1)}
        self.assertIn("oh", names)

    def test_reach_softens_big_mouths(self):
        self.assertLess(h.reach(0.55, "ah"), h.reach(1.0, "ah"))


class Behaviour(unittest.TestCase):
    def test_colour_rules(self):
        holo, c = make()
        self.assertEqual(holo.colour_wanted(False, False, c.t), "cyan")
        self.assertEqual(holo.colour_wanted(True, False, c.t), "green")
        self.assertEqual(holo.colour_wanted(True, True, c.t), "amber")
        holo.heard_her_name(c.t)
        self.assertEqual(holo.colour_wanted(False, False, c.t + 1), "green")
        self.assertEqual(holo.colour_wanted(False, False, c.t + h.LISTEN_SECONDS + 1), "cyan")

    def test_power_up_and_down(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertGreater(holo.power, 0.95)
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=False, now=c.t)
        self.assertLess(holo.power, 0.03)

    def test_speaking_then_closed_mouth(self):
        holo, c = make()
        holo.speech_started("Hello commander", c.t)
        self.assertTrue(holo.speaking)
        c.t += 1.2
        holo.speech_finished(c.t)
        self.assertFalse(holo.speaking)
        self.assertIsNone(holo._mouth_goal(c.t + 0.5))          # no little grin after she stops
        self.assertIsNone(holo._mouth_goal(c.t + h.SMILE_SECONDS + 1))

    def test_speed_is_learned_within_limits(self):
        holo, c = make()
        holo.speech_started("a long line of talking here", c.t)
        c.t += 30
        holo.speech_finished(c.t)
        self.assertGreaterEqual(holo.cps, 8.0)

    def test_render_has_key_pixels_and_picture(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        frame = holo.render(c.t)
        self.assertEqual(frame.dtype, np.uint8)
        self.assertEqual(frame.shape, (holo.assets.window_h, holo.assets.window_w, 3))
        key = np.all(frame == np.array(h.KEY, dtype=np.uint8), axis=2)
        self.assertGreater(key.mean(), 0.2)         # lots of see-through
        self.assertLess(key.mean(), 0.95)           # but she is drawn

    def test_powered_down_is_all_see_through(self):
        holo, c = make()
        frame = holo.render(c.t)                    # power is 0 at the start
        key = np.all(frame == np.array(h.KEY, dtype=np.uint8), axis=2)
        self.assertGreater(key.mean(), 0.97)


class Bus:
    def __init__(self): self.handlers = {}
    def subscribe(self, name, fn): self.handlers.setdefault(name, []).append(fn)
    def fire(self, name, **data):
        class E: pass
        e = E(); e.data = data
        for fn in self.handlers.get(name, []): fn(e)


class Settings:
    def __init__(self, **v): self.values = v
    def get(self, key, default=None): return self.values.get(key, default)
    def set(self, key, value): self.values[key] = value
    def save(self): pass


class App:
    def __init__(self, **settings):
        self.bus = Bus()
        self.settings = Settings(**settings)
        self.state = type("S", (), {"gui_focus": 0, "game_quit": False})()
        self.ptt = None
        self.ask = type("A", (), {"pending": {}})()
        self.brain = type("B", (), {"thinking": 0})()


class Feed(unittest.TestCase):
    def setUp(self):
        self.holo, self.c = make()
        self.app = App()
        self.feed = HologramFeed(self.app, lambda: self.holo)
        self.feed.attach()

    def test_speech_events_drive_the_mouth(self):
        self.app.bus.fire("speech.started", text="Hello there commander")
        self.app.bus.fire("speech.audio", what="start", text="Hello there commander", seconds=None)
        self.assertTrue(self.holo.speaking)
        self.app.bus.fire("speech.finished")
        self.assertFalse(self.holo.speaking)

    def test_name_alone_means_listening_but_a_command_does_not(self):
        self.app.bus.fire("voice.heard", wake=True, command="")
        self.assertGreater(self.holo.listen_until, 0)
        self.holo.listen_until = 0
        self.app.bus.fire("voice.heard", wake=True, command="landing gear")
        self.assertEqual(self.holo.listen_until, 0)

    def test_open_mic_alone_is_not_listening(self):
        class Ptt:
            def __init__(self, on, held): self.on, self.held = on, held
            def enabled(self): return self.on
            def is_open(self): return self.held
        self.app.ptt = Ptt(False, True)             # always-open mic style: not green
        self.assertFalse(self.feed.listening())
        self.app.ptt = Ptt(True, True)
        self.assertTrue(self.feed.listening())
        self.app.ptt = Ptt(True, False)
        self.assertFalse(self.feed.listening())

    def test_question_pending_is_listening(self):
        self.app.ask.pending = {"open": True}
        self.assertTrue(self.feed.listening())

    def test_listening_colour_can_be_off(self):
        self.app.settings.values["hologram.listening_colour"] = False
        self.app.ask.pending = {"open": True}
        self.assertFalse(self.feed.listening())

    def test_thinking_and_focus(self):
        self.assertFalse(self.feed.thinking())
        self.app.brain.thinking = 1
        self.assertTrue(self.feed.thinking())
        self.app.state.gui_focus = 6
        self.assertEqual(self.feed.gui_focus(), 6)
        self.app.state.game_quit = True
        self.assertTrue(self.feed.game_quit())

    def test_a_broken_event_never_raises(self):
        self.holo = None
        self.app.bus.fire("speech.started", text="hi")      # no hologram yet: just ignored


class Effects(unittest.TestCase):
    def powered(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        return holo, c

    def test_lights_stay_below_her_chest_and_come_from_the_ring(self):
        holo, c = self.powered()
        a = holo.assets
        near = np.zeros((a.window_h, a.window_w), dtype=np.float32)
        far = np.zeros_like(near)
        for step in range(12):
            holo._sparks(c.t + step * 0.7, near, far)
        rows = np.where((near + far).max(axis=1) > 0)[0]
        self.assertGreater(len(rows), 20)
        self.assertGreaterEqual(rows.min(), h.PAD_TOP + a.height * 0.64 - 3)      # never higher than her chest
        self.assertLessEqual(rows.max(), h.PAD_TOP + a.height + 20)               # starts down at the ring

    def test_rings_and_lights_do_not_flicker(self):
        holo, c = self.powered()
        holo.fx_turn = False
        holo.flicker_on = True
        holo.rng = random.Random(5)
        a = holo.assets
        cy = h.PAD_TOP + a.height + 14
        samples = []
        for step in range(30):
            frame = holo.render(c.t + step * 0.013)        # same time of the lights, tiny steps: only her flicker changes
            samples.append(int(frame[cy + 1:cy + 3, :, :].astype(int).sum()))
        self.assertLess(max(samples) - min(samples), max(samples) * 0.05 + 1)

    def test_effects_can_be_switched_off(self):
        holo, c = self.powered()
        holo.fx_beam = False
        holo.fx_turn = False
        self.assertEqual(holo.render(c.t).shape[2], 3)


class ExactTiming(unittest.TestCase):
    def test_phonemes_from_a_piece(self):
        from tts.kokoro_tts import piece_phonemes

        class Out: pred_dur = [2, 4, 6, 3, 5]
        class Piece:
            phonemes = "hɛj"
            output = Out()
        got = piece_phonemes(Piece(), 1.0)
        self.assertEqual([c for c, _ in got], ["", "h", "ɛ", "j", ""])
        self.assertAlmostEqual(sum(s for _, s in got), 1.0, places=5)
        self.assertGreater(got[2][1], got[1][1])             # the vowel lasts longer than the h

    def test_wrong_numbers_mean_no_timing(self):
        from tts.kokoro_tts import piece_phonemes

        class Out: pred_dur = [1, 2]
        class Piece:
            phonemes = "abc"
            output = Out()
        self.assertIsNone(piece_phonemes(Piece(), 1.0))
        self.assertIsNone(piece_phonemes(object(), 1.0))

    def test_track_follows_the_sounds(self):
        track = h.track_from_phonemes([("", 0.1), ("p", 0.05), ("ɑ", 0.2), ("ˈ", 0.02), ("m", 0.05), (" ", 0.1)])
        shapes = [shape for _, _, shape in track]
        self.assertEqual(shapes, [None, "pressed", "ah", "pressed", None])
        self.assertAlmostEqual(track[2][1] - track[2][0], 0.22, places=5)      # the stress mark lengthened the vowel
        self.assertAlmostEqual(h.track_length(track), 0.52, places=5)

    def test_timeline_mixes_exact_and_text_pieces(self):
        entries = [(0.5, None, [("", 0.1), ("ɑ", 0.3), ("", 0.1)]), (0.3, "", None), (0.8, "hello there", None)]
        track = h.track_from_timeline(entries)
        self.assertAlmostEqual(h.track_length(track), 1.6, places=5)
        self.assertEqual(h.shape_at(track, 0.2), "ah")
        self.assertIsNone(h.shape_at(track, 0.6))                 # the pause between parts: mouth closed
        self.assertIsNotNone([s for _, _, s in track if s])

    def test_exact_timing_replaces_the_guess_and_is_not_stretched(self):
        holo, c = make()
        holo.speech_started("Hello there commander", c.t)
        holo.set_timeline([(1.0, None, [("", 0.2), ("ɑ", 0.6), ("", 0.2)])])
        self.assertTrue(holo.exact_track)
        holo.set_duration(5.0)
        self.assertEqual(holo.time_scale, 1.0)
        self.assertEqual(holo._mouth_goal(c.t + 0.5), "ah")

    def test_the_voice_cache_keeps_the_timing_next_to_the_sound(self):
        import tempfile, pathlib
        from tts.kokoro_tts import KokoroTTS
        folder = pathlib.Path(tempfile.mkdtemp())
        tts = KokoroTTS(folder / "p.pt", folder / "r.mp3", pipeline_factory=lambda: None, cache_dir=folder / "cache")
        tts._cache_save("hello", 1.0, np.ones(100, dtype=np.float32) * 0.1, [("", 0.1), ("h", 0.2)])
        self.assertEqual(tts._cache_load_phonemes("hello", 1.0), [("", 0.1), ("h", 0.2)])
        self.assertIsNone(tts._cache_load_phonemes("other", 1.0))


class FollowsTheSound(unittest.TestCase):
    def talking(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        holo.speech_started("Hello commander how are you today", c.t)
        holo.set_timeline([(2.0, None, [("", 0.2), ("ɑ", 1.0), ("m", 0.6), ("", 0.2)])])
        return holo, c

    def test_lips_follow_the_sound_not_the_clock(self):
        holo, c = self.talking()
        holo.add_levels([(c.t, [0.1] * 4, 0.5, 0.1)])               # the speakers have been given sound 0.5 s into the line
        self.assertAlmostEqual(holo._elapsed(c.t + 0.02), 0.52, places=2)
        self.assertEqual(holo._mouth_goal(c.t + 0.02), "ah")

    def test_a_stall_stops_the_lips_instead_of_running_ahead(self):
        holo, c = self.talking()
        holo.add_levels([(c.t, [0.1] * 4, 0.5, 0.1)])
        c.t += 3.0                                                   # the voice is still being made: no new sound for 3 s
        self.assertIsNone(holo._mouth_goal(c.t))
        self.assertTrue(holo.stalled)
        self.assertAlmostEqual(holo._elapsed(c.t), 0.6, places=2)    # frozen where the sound stopped
        holo.add_levels([(c.t, [0.1] * 4, 0.6, 0.1)])                # sound starts again
        self.assertIsNotNone(holo._mouth_goal(c.t + 0.01))
        self.assertFalse(holo.stalled)

    def test_without_word_from_the_speakers_it_uses_the_clock(self):
        holo, c = self.talking()
        self.assertAlmostEqual(holo._elapsed(c.t + 0.7), 0.7, places=3)

    def test_timing_that_arrives_before_the_sound_is_kept(self):
        holo, c = make()
        app = App()
        feed = HologramFeed(app, lambda: holo)
        feed.attach()
        app.bus.fire("speech.started", text="Hello there", audio="")
        app.bus.fire("speech.audio", what="timeline", text="", seconds=[(1.0, None, [("", 0.1), ("ɑ", 0.8), ("", 0.1)])])
        app.bus.fire("speech.audio", what="length", text="", seconds=1.0)
        app.bus.fire("speech.audio", what="start", text="Hello there", seconds=None)
        self.assertTrue(holo.exact_track)
        self.assertEqual(holo._mouth_goal(holo.track_start + 0.5), "ah")


class FlipBook(unittest.TestCase):
    def test_pictures_load_and_loop(self):
        a = h.Assets(225)
        frames, shifts, fps = a.idle
        self.assertGreater(len(frames), 30)
        self.assertEqual(len(frames), len(shifts))
        self.assertEqual(frames[0].shape, (a.height, a.width, 3))
        self.assertGreater(fps, 10)

    def test_eases_to_still_when_she_talks_and_back(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertGreater(holo.idle_mix, 0.95)
        holo.speech_started("Hello commander how are you today", c.t)
        for _ in range(20):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertLess(holo.idle_mix, 0.05)
        holo.speech_finished(c.t)
        for _ in range(200):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertGreater(holo.idle_mix, 0.95)

    def test_can_be_switched_off(self):
        holo, c = make()
        holo.idle_on = False
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertLess(holo.idle_mix, 0.05)
        self.assertEqual(holo.render(c.t).shape[2], 3)

    def test_head_shifts_are_small(self):
        a = h.Assets(225)
        for dx, dy in a.idle[1]:
            self.assertLess(abs(dx), a.width * 0.1)
            self.assertLess(abs(dy), a.height * 0.1)

    def test_missing_pictures_mean_no_flip_book(self):
        import tempfile, shutil, pathlib
        folder = pathlib.Path(tempfile.mkdtemp())
        try:
            for f in h.ASSET_DIR.glob("*"):
                if f.is_file():
                    shutil.copy(f, folder / f.name)
            (folder / "idle.json").unlink(missing_ok=True)
            a = h.Assets(225, folder)
            self.assertEqual(a.idle[0], [])
            holo = h.Hologram(a)
            self.assertEqual(holo.render().shape[2], 3)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class RealLoudness(unittest.TestCase):
    def talking(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        holo.speech_started("Hello commander how are you today", c.t)
        return holo, c

    def feed_levels(self, holo, start, values, step=0.025):
        holo.add_levels([(start + i * 0.1, values[i * 4:(i + 1) * 4]) for i in range(len(values) // 4)])

    def test_a_pause_closes_the_mouth_and_loud_opens_it(self):
        holo, c = self.talking()
        loud, quiet = [0.15] * 8, [0.001] * 8
        self.feed_levels(holo, c.t, loud + quiet)
        for _ in range(6):                                   # 0.15 s into the loud sound
            c.t += 0.025
            holo.tick(powered=True, now=c.t)
        self.assertTrue(holo.levels_live)
        self.assertGreater(holo.level_open, 0.8)
        for _ in range(24):                                  # now the quiet part
            c.t += 0.025
            holo.tick(powered=True, now=c.t)
        self.assertLess(holo.level_open, 0.15)

    def test_without_numbers_it_falls_back_to_the_text_timing(self):
        holo, c = self.talking()
        c.t += 0.1
        holo.tick(powered=True, now=c.t)
        self.assertFalse(holo.levels_live)
        self.assertEqual(holo.level_open, 1.0)

    def test_old_numbers_are_ignored(self):
        holo, c = self.talking()
        self.feed_levels(holo, c.t - 5.0, [0.1] * 4)
        c.t += 0.1
        holo.tick(powered=True, now=c.t)
        self.assertFalse(holo.levels_live)

    def test_loudness_slices(self):
        from tts.kokoro_tts import loudness_slices
        audio = np.concatenate([np.zeros(600), np.ones(600) * 0.2, np.zeros(600), np.ones(600) * 0.2]).astype(np.float32)
        got = loudness_slices(audio)
        self.assertEqual(len(got), 4)
        self.assertLess(got[0], 0.01)
        self.assertAlmostEqual(got[1], 0.2, places=2)

    def test_speech_manager_hands_levels_over_once(self):
        from tts.speech_manager import SpeechManager
        m = SpeechManager({}, Settings())
        m._audio_note("levels", [0.1, 0.2, 0.1, 0.0], "x")
        taken = m.take_levels()
        self.assertEqual(len(taken), 1)
        self.assertEqual(taken[0][1], [0.1, 0.2, 0.1, 0.0])
        self.assertEqual(m.take_levels(), [])


class LipTiming(unittest.TestCase):
    def test_lips_wait_for_the_real_sound(self):
        holo, c = make()
        app = App()
        feed = HologramFeed(app, lambda: holo)
        feed.attach()
        app.bus.fire("speech.started", text="Hello commander", audio="")
        self.assertFalse(holo.speaking)                      # still making the sound: no lips yet
        app.bus.fire("speech.audio", what="start", text="Hello commander", seconds=None)
        self.assertTrue(holo.speaking)
        app.bus.fire("speech.audio", what="end", text="", seconds=None)
        self.assertFalse(holo.speaking)

    def test_recorded_line_starts_at_once(self):
        holo, c = make()
        app = App()
        HologramFeed(app, lambda: holo).attach()
        app.bus.fire("speech.started", text="Docking granted", audio="dock.mp3")
        self.assertTrue(holo.speaking)

    def test_mouth_is_stretched_to_the_real_length(self):
        holo, c = make()
        holo.speech_started("Hello commander how are you", c.t)
        natural = h.track_length(holo.track)
        holo.set_duration(natural * 2)
        self.assertAlmostEqual(holo.time_scale, 2.0, places=2)
        # one natural length in, the mouth is only half way through, so it is still moving
        self.assertTrue(holo.speaking)
        self.assertIsNotNone(holo._mouth_goal(c.t + natural * 0.9) or "x")
        self.assertIsNone(holo._mouth_goal(c.t + natural * 2 + 2))

    def test_stretch_is_limited(self):
        holo, c = make()
        holo.speech_started("Hello commander", c.t)
        holo.set_duration(9999)
        self.assertLessEqual(holo.time_scale, 3.0)
        holo.set_duration(0.0001)
        self.assertGreaterEqual(holo.time_scale, 0.4)


class GameFocus(unittest.TestCase):
    def setUp(self):
        self.feed = HologramFeed(App(), lambda: None)
        self.title = "Elite - Dangerous (CLIENT)"
        self.feed.title_provider = lambda: self.title
        self.feed.boot_seconds = 20.0

    def test_waits_after_start_then_powers_up(self):
        self.assertFalse(self.feed.game_in_focus(1000.0))        # game just appeared: she is still starting up
        self.assertFalse(self.feed.game_in_focus(1010.0))
        self.assertTrue(self.feed.game_in_focus(1021.0))

    def test_powers_down_when_you_leave_the_game(self):
        self.feed.game_in_focus(1000.0)
        self.assertTrue(self.feed.game_in_focus(1030.0))
        self.title = "Discord"
        self.assertFalse(self.feed.game_in_focus(1031.0))
        self.title = "Elite - Dangerous (CLIENT)"
        self.assertTrue(self.feed.game_in_focus(1032.0))         # back: powers up at once, no second start-up wait

    def test_new_start_waits_again(self):
        self.feed.game_in_focus(1000.0)
        self.assertTrue(self.feed.game_in_focus(1030.0))
        self.feed.game_gone()
        self.assertFalse(self.feed.game_in_focus(1031.0))

    def test_game_in_front_overrules_a_wrong_closed_flag(self):
        self.feed.app.state.game_quit = True           # Starling started while the game was idle: the journal looked old
        self.assertFalse(self.feed.game_quit())          # but Elite is the window in front, so it is running
        self.title = "Discord"
        self.feed._focus_at = 0
        self.assertTrue(self.feed.game_quit())

    def test_unknown_window_keeps_her_on(self):
        self.feed.title_provider = lambda: None
        self.assertTrue(self.feed.game_in_focus(5.0))


class Voice(unittest.TestCase):
    def test_phrases(self):
        for t in ("show the hologram", "turn on the hologram", "switch the hologram on", "please show your hologram"):
            self.assertEqual(which(t), "holo_on", t)
        for t in ("hide the hologram", "turn off the hologram", "switch the hologram off", "close the hologram"):
            self.assertEqual(which(t), "holo_off", t)
        self.assertIsNone(which("what is a hologram"))

    def test_setting_flips(self):
        s = Settings(**{"hologram.enabled": False})
        said = []
        nar = type("N", (), {"say": lambda self, k, f=None: said.append(k)})()
        asked = []
        v = WindowVoice(s, asked.append, nar)
        v.try_handle("show the hologram")
        self.assertEqual(asked, ["hologram_test"])          # she is shown for a few seconds as proof
        self.assertTrue(s.get("hologram.enabled"))
        v.try_handle("hide the hologram")
        self.assertFalse(s.get("hologram.enabled"))
        self.assertEqual(said, ["Window_HologramShown", "Window_HologramHidden"])

    def test_lines_exist(self):
        import json
        data = json.load(open("voicepacks/default/streaming.json"))
        self.assertTrue(data["Window_HologramShown"] and data["Window_HologramHidden"])


class Defaults(unittest.TestCase):
    def test_on_by_default(self):
        from core.settings import DEFAULTS
        self.assertTrue(DEFAULTS["hologram"]["enabled"])

class BackAndForthClips(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "clips" / "nod").mkdir(parents=True)
        for n in range(5):
            Image.new("RGB", (8, 8), (n * 40, 0, 0)).save(self.dir / "clips" / "nod" / ("%03d.jpg" % n), quality=95)

    def load(self, back):
        (self.dir / "clips.json").write_text(json.dumps({"nod": {"frames": 5, "fps": 12, **({"back": True} if back else {})}}))
        return h.load_clip(self.dir, "nod", 8, 8)

    def test_a_clip_that_does_not_come_home_is_played_back(self):
        frames = self.load(True)
        self.assertEqual(len(frames), 8)                          # 0 1 2 3 4 3 2 1
        self.assertIs(frames[5], frames[3])                       # the same picture again, not a copy
        self.assertIs(frames[-1], frames[1])

    def test_a_normal_clip_is_not_changed(self):
        self.assertEqual(len(self.load(False)), 5)

    def test_a_recorded_clip_beats_the_built_in_gesture(self):
        h.clear_clips()
        holo, c = make()
        holo.power = 1.0
        self.assertIn("shake", holo.assets.clips)
        holo.rng = type("Sure", (), {"random": lambda self: 0.0, "choice": lambda self, x: x[0], "uniform": lambda self, a, b: a})()
        self.assertTrue(holo.react_to("DockingDenied", now=c.t + 100))
        self.assertEqual(holo.pose_wanted[0], "shake")
        self.assertIsNone(holo.g_name)
        h.clear_clips()


class BounceAndIdleTests(unittest.TestCase):
    def test_the_bounce_setting_scales_the_dip(self):
        holo, c = make()
        holo.nod = 1.0
        holo.bounce = 1.0
        full = holo._nod_offsets(c.t, 1.0)[1]
        holo.bounce = 0.5
        half = holo._nod_offsets(c.t, 1.0)[1]
        holo.bounce = 0.0
        none = holo._nod_offsets(c.t, 1.0)[1]
        self.assertGreater(full, 0)
        self.assertAlmostEqual(half, full / 2.0)
        self.assertEqual(none, 0.0)

    def test_the_default_bounce_is_about_half_of_the_old_one(self):
        holo, c = make()
        self.assertEqual(holo.bounce, 0.5)

    def test_livelier_means_shorter_waits(self):
        holo, c = make()
        holo.idle_scale = 0.4
        holo._rest(c.t)
        self.assertLessEqual(holo.bored_after, h.BORED_AFTER[1] * 0.4)
        holo.idle_scale = 0.2
        holo._rest(c.t)
        self.assertLessEqual(holo.bored_after, h.BORED_AFTER[1] * 0.2)

    def test_the_idle_pool_has_small_fidgets_that_exist(self):
        holo, c = make()
        self.assertIn("eyes_left", h.BORED_CLIPS)
        self.assertTrue(any(n in holo.assets.clips for n in h.BORED_CLIPS if n.startswith(("eyes", "glance"))))

    def test_the_settings_exist(self):
        from core.settings import DEFAULTS
        self.assertEqual(DEFAULTS["hologram"]["talk_bounce"], 50)
        self.assertEqual(DEFAULTS["hologram"]["idle_wait"], 40)


class HeadClipToolTests(unittest.TestCase):
    def test_the_morph_goes_from_one_picture_to_the_other(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import make_head_clips as mhc
        a = Image.new("RGB", (64, 96), (0, 0, 0))
        b = Image.new("RGB", (64, 96), (200, 200, 200))
        frames = mhc.morph_frames(a, b, 5)
        means = [float(np.asarray(f).mean()) for f in frames]
        self.assertEqual(len(frames), 5)
        self.assertEqual(means, sorted(means))
        self.assertLess(means[0], 1)
        self.assertGreater(means[-1], 190)

    def test_a_red_speck_at_the_top_is_removed_but_orange_eyes_are_not(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import make_head_clips as mhc
        a = np.zeros((96, 64, 3), np.uint8)
        a[2, 50] = (255, 0, 0)               # the speck
        a[50, 20] = (200, 120, 60)           # an eye
        cleaned = np.asarray(mhc.clean(Image.fromarray(a)))
        self.assertEqual(tuple(cleaned[2, 50]), (0, 0, 0))
        self.assertEqual(tuple(cleaned[50, 20]), (200, 120, 60))


class ClipToolTests(unittest.TestCase):
    def test_end_gap(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import make_clips
        a, b = Image.new("RGB", (64, 96), (0, 0, 0)), Image.new("RGB", (64, 96), (100, 100, 100))
        self.assertEqual(make_clips.end_gap([a, a]), 0.0)
        self.assertGreater(make_clips.end_gap([a, b]), make_clips.BACK_GAP)


if __name__ == "__main__":
    unittest.main()


class SofterLips(unittest.TestCase):
    def test_consonants_only_half_open_and_p_b_m_close(self):
        self.assertEqual(h.VOWEL["t"], "soft")
        self.assertEqual(h.PHONEME_SHAPES["n"], "soft")
        self.assertEqual(h.VOWEL["m"], "pressed")
        self.assertEqual(h.targets("soft"), {"eh": h.SOFT})
        self.assertEqual(h.targets("ah"), {"ah": 1.0})
        self.assertEqual(h.targets(None), {})

    def test_a_very_short_sound_lends_its_time_to_the_one_before(self):
        track = [(0.0, 0.2, "ah"), (0.2, 0.21, "oo"), (0.21, 0.4, "ee")]
        self.assertEqual(h.mouth_at(track, 0.205), "ah")
        self.assertEqual(h.mouth_at(track, 0.3), "ee")

    def test_p_b_m_are_never_skipped(self):
        track = [(0.0, 0.2, "ah"), (0.2, 0.21, "pressed"), (0.21, 0.4, "ee")]
        self.assertEqual(h.mouth_at(track, 0.205), "pressed")

    def test_short_pause_keeps_the_mouth_long_pause_closes_it(self):
        short = [(0.0, 0.2, "ah"), (0.2, 0.28, None), (0.28, 0.5, "ee")]
        long = [(0.0, 0.2, "ah"), (0.2, 0.6, None), (0.6, 0.8, "ee")]
        self.assertEqual(h.mouth_at(short, 0.24), "ah")
        self.assertIsNone(h.mouth_at(long, 0.4))

    def test_mouth_starts_a_little_early(self):
        holo, c = make()
        holo.speech_started("x", c.t)
        holo.track = [(0.0, 0.3, None), (0.3, 0.6, "ah")]
        holo.exact_track = True
        c.t += 0.3 - h.LEAD + 0.01
        self.assertEqual(holo._mouth_goal(c.t), "ah")

    def test_opening_is_quicker_than_closing(self):
        self.assertLess(h.ATTACK, h.RELEASE)

    def test_jaw_drops_with_an_open_mouth_and_picture_changes(self):
        holo, c = make()
        holo.power = 1.0
        holo.idle_on = False
        holo.fx_turn = holo.fx_beam = holo.flicker_on = False
        quiet = holo.render(c.t).copy()
        self.assertEqual(holo._jaw_drop(), 0.0)
        holo.weights["ah"] = 1.0
        self.assertGreater(holo._jaw_drop(), 0.5)
        self.assertEqual(holo.render(c.t).shape, quiet.shape)

    def test_head_nods_only_while_talking(self):
        holo, c = make()
        holo.power = 1.0
        for _ in range(10):
            c.t += 0.05
            holo.tick(now=c.t)
        self.assertLess(holo.nod, 0.01)
        holo.speech_started("Hello commander how are you today", c.t)
        holo.track = [(0.0, 5.0, "ah")]
        holo.exact_track = True
        for _ in range(20):
            c.t += 0.05
            holo.tick(now=c.t)
        self.assertGreater(holo.nod, 0.3)
        holo.render(c.t)                                     # the nod and sway must draw without a problem
        holo.talk_motion = False
        holo.render(c.t)


class PoseClips(unittest.TestCase):
    def setUp(self):
        h.clear_clips()
        self.holo, self.c = make()
        self.holo.power = 1.0
        for name in h.PINNED:
            h.get_clip(self.holo.assets, name, wait=True)

    def tearDown(self):
        h.clear_clips()

    def run_for(self, seconds, **kw):
        for _ in range(int(seconds / 0.05)):
            self.c.t += 0.05
            self.holo.tick(now=self.c.t, **kw)

    def test_the_clip_files_are_there(self):
        self.assertEqual(sorted(self.holo.assets.clips), sorted(["blow_kiss", "bored1", "bored2", "brow_down", "brow_up", "glance_left", "glance_right", "listening", "nod", "pleased", "salute", "shake", "thinking", "tilt",
                                                                                                  "eyes_left", "eyes_right", "wink", "smirk", "sad", "angry", "worried", "yawn", "awe", "ponder", "eyeroll", "blush", "sleepy", "laugh",
                                                                                                  "glance_up", "tilt_right", "eyes_up", "eyes_down", "nod_twice", "suspicious", "curious", "giggle", "flirty", "disagree", "daydream", "hair_flick", "hand_to_temple", "hands_resting", "content_smile", "listen_tilt", "idle_alt1", "hair_flick2", "check_mirror", "adjust_suit", "adjust_suit_rare", "cheer", "excited", "facepalm", "point", "shrug", "startle", "thumbs_up"]))

    def test_thinking_plays_then_leaves_when_the_answer_comes(self):
        self.run_for(0.5, thinking=True)
        self.assertEqual(self.holo.clip, "thinking")
        self.assertGreater(self.holo.clip_mix, 0.9)
        picture = self.holo.render(self.c.t)
        self.assertEqual(picture.shape[0], self.holo.assets.window_h)
        self.run_for(1.0, thinking=False)
        self.assertIsNone(self.holo.clip)
        self.assertLess(self.holo.clip_mix, 0.05)

    def test_thinking_clip_ends_by_itself_and_is_not_repeated(self):
        self.run_for(0.2, thinking=True)
        self.assertEqual(self.holo.clip, "thinking")
        self.run_for(7.0, thinking=True)
        self.assertIsNone(self.holo.clip)
        self.run_for(1.0, thinking=True)
        self.assertIsNone(self.holo.clip)                   # the same thought does not replay it

    def test_listening_clip_follows_her_name(self):
        self.holo.heard_her_name(self.c.t)
        self.run_for(0.5)
        self.assertEqual(self.holo.clip, "listening")

    def test_speaking_cuts_a_clip_off_quickly(self):
        self.run_for(0.5, thinking=True)
        self.holo.speech_started("Here you go", self.c.t)
        self.run_for(0.4, thinking=False)
        self.assertIsNone(self.holo.clip)
        self.assertLess(self.holo.clip_mix, 0.1)

    def test_mouth_pictures_are_hidden_while_a_clip_plays(self):
        self.run_for(1.0, thinking=True)
        self.holo.weights["ah"] = 1.0
        before = self.holo.clip_mix
        self.assertGreater(before, 0.9)
        self.holo.render(self.c.t)                          # draws without error with the clip on top

    def test_bored_after_a_long_quiet_time(self):
        self.holo.assets.clips = ["bored1", "bored2"]
        old, h.CLIP_LRU = h.CLIP_LRU, 2                       # both stay loaded here, so the test does not wait for a background load
        self.addCleanup(setattr, h, "CLIP_LRU", old)
        for name in ("bored1", "bored2"):
            h.get_clip(self.holo.assets, name, wait=True)
        self.run_for(h.BORED_AFTER[0] - 5)
        self.assertIsNone(self.holo.clip)                      # not bored yet
        seen = set()
        for _ in range(int((h.BORED_AFTER[1] - h.BORED_AFTER[0] + 20) / 0.1)):
            self.c.t += 0.1
            self.holo.tick(now=self.c.t)
            seen.add(self.holo.clip)
        self.assertTrue(seen & {"bored1", "bored2"})

    def _both_loaded(self, names):
        self.holo.assets.clips = list(names)
        old, h.CLIP_LRU = h.CLIP_LRU, len(names) + 1
        self.addCleanup(setattr, h, "CLIP_LRU", old)
        for name in names:
            h.get_clip(self.holo.assets, name, wait=True)

    def _bored_clips_seen(self, naughty, seconds=400):
        self.holo.naughty = naughty
        seen = []
        for _ in range(int(seconds / 0.1)):
            self.c.t += 0.1
            self.holo.tick(now=self.c.t)
            if self.holo.clip and (not seen or seen[-1] != self.holo.clip):
                seen.append(self.holo.clip)
        return seen

    def test_the_rare_suit_clip_never_plays_unless_naughty_is_ticked(self):
        names = ["adjust_suit", "adjust_suit_rare", "blow_kiss"]
        self._both_loaded(names)
        seen = self._bored_clips_seen(False)
        self.assertIn("adjust_suit", seen)
        self.assertNotIn("adjust_suit_rare", seen)
        self.assertNotIn("blow_kiss", seen)

    def test_the_naughty_clips_can_play_when_it_is_ticked(self):
        class Lucky(random.Random):
            def random(self): return 0.0
        names = ["adjust_suit", "adjust_suit_rare", "blow_kiss"]
        self._both_loaded(names)
        self.holo.rng = Lucky()
        self.assertTrue(set(self._bored_clips_seen(True)) & {"adjust_suit_rare", "blow_kiss"})

    def test_a_second_clip_can_follow_the_first(self):
        class Lucky(random.Random):
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
        names = ["idle_alt1", "hair_flick2"]
        self._both_loaded(names)
        self.holo.rng = Lucky()
        self.holo.start_clip("idle_alt1", self.c.t, partners=names)
        self.assertEqual(self.holo.clip_queue, ["hair_flick2"])
        self.run_for(len(self.holo.clip_frames) / self.holo.clip_fps + 0.5)
        self.assertEqual(self.holo.clip, "hair_flick2")                  # it started at once, no gap
        self.holo.stop_clip()
        self.assertEqual(self.holo.clip_queue, [])

    def test_no_second_clip_when_the_roll_says_no(self):
        class Unlucky(random.Random):
            def random(self): return 0.99
        names = ["idle_alt1", "hair_flick2"]
        self._both_loaded(names)
        self.holo.rng = Unlucky()
        self.holo.start_clip("idle_alt1", self.c.t, partners=names)
        self.assertEqual(self.holo.clip_queue, [])

    def test_a_naughty_clip_is_never_chained_when_not_ticked(self):
        class Lucky(random.Random):
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
        names = ["idle_alt1", "adjust_suit_rare"]
        self._both_loaded(names)
        self.holo.rng = Lucky()
        self.holo.naughty = False
        self.holo.start_clip("idle_alt1", self.c.t, partners=names)
        self.assertEqual(self.holo.clip_queue, [])

    def test_a_happy_reaction_picks_from_the_happy_clips_and_does_not_wait(self):
        class Lucky(random.Random):
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
        self._both_loaded(["cheer", "excited"])
        self.holo.rng = Lucky()
        self.assertTrue(self.holo.react_to("MissionCompleted", self.c.t))
        self.assertEqual(self.holo.pose_wanted[0], "cheer")
        self.run_for(1.0)
        self.assertEqual(self.holo.clip, "cheer")                       # no waiting for the idle gap

    def test_the_startle_clip_plays_at_once(self):
        class Lucky(random.Random):
            def random(self): return 0.0
        self._both_loaded(["startle"])
        self.holo.rng = Lucky()
        self.assertTrue(self.holo.react_to("Interdicted", self.c.t))
        self.assertEqual(self.holo.clip, "startle")

    def test_all_the_groups_name_real_clips(self):
        for group in h.REACTION_GROUPS.values():
            self.assertTrue(group)
        self.assertEqual(set(h.NAUGHTY_CLIPS), {"adjust_suit_rare", "blow_kiss"})
        self.assertNotIn("adjust_suit_rare", h.BORED_CLIPS)
        self.assertNotIn("blow_kiss", h.BORED_CLIPS)

    def test_pleased_after_a_long_line(self):
        class Always(random.Random):
            def random(self): return 0.0
        self.holo.rng = Always()
        h.get_clip(self.holo.assets, "pleased", wait=True)
        self.holo.speech_started("Here is a long answer for you commander", self.c.t)
        self.c.t += 3.0
        self.holo.speech_finished(self.c.t)
        seen = set()
        for _ in range(int((h.POSE_GAP + h.SMILE_SECONDS + 3) / 0.1)):
            self.c.t += 0.1
            self.holo.tick(now=self.c.t)
            seen.add(self.holo.clip)
        self.assertIn("pleased", seen)

    def test_switched_off_means_no_clip(self):
        self.holo.poses_on = False
        self.run_for(1.0, thinking=True)
        self.assertIsNone(self.holo.clip)

    def test_missing_clips_do_not_break_anything(self):
        import tempfile, shutil
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("base.jpg", "hologram.json"):
                shutil.copy(h.ASSET_DIR / name, Path(tmp) / name)
            for png in h.ASSET_DIR.glob("*.png"):
                shutil.copy(png, Path(tmp) / png.name)
            holo = h.Hologram(h.Assets(225, tmp), random.Random(1), self.c)
            holo.power = 1.0
            for _ in range(20):
                self.c.t += 0.05
                holo.tick(thinking=True, now=self.c.t)
            self.assertIsNone(holo.clip)
            holo.render(self.c.t)

    def test_only_a_few_clips_stay_in_memory(self):
        a = self.holo.assets
        for name in ("pleased", "bored1", "bored2"):
            h.get_clip(a, name, wait=True)
        kept = [key[2] for key in h._CLIPS]
        self.assertIn("thinking", kept)
        self.assertIn("listening", kept)
        self.assertEqual(len([n for n in kept if n not in h.PINNED]), h.CLIP_LRU)


class ForcedClips(unittest.TestCase):
    def test_a_test_clip_plays_to_the_end_even_with_poses_off_and_no_thinking(self):
        h.clear_clips()
        holo, c = make()
        holo.power = 1.0
        holo.poses_on = False
        h.get_clip(holo.assets, "thinking", wait=True)
        self.assertTrue(holo.start_clip("thinking", c.t, forced=True))
        for _ in range(40):
            c.t += 0.1
            holo.tick(thinking=False, now=c.t)
        self.assertEqual(holo.clip, "thinking")                 # 4 seconds in, still playing
        self.assertGreater(holo.clip_mix, 0.9)
        for _ in range(60):
            c.t += 0.1
            holo.tick(thinking=False, now=c.t)
        self.assertIsNone(holo.clip)
        self.assertFalse(holo.clip_forced)
        h.clear_clips()


class Salute(unittest.TestCase):
    def setUp(self):
        h.clear_clips()
        self.holo, self.c = make()
        self.holo.power = 1.0
        h.get_clip(self.holo.assets, "salute", wait=True)
        self.addCleanup(h.clear_clips)

    def run_for(self, seconds, **kw):
        for _ in range(int(seconds / 0.05)):
            self.c.t += 0.05
            self.holo.tick(now=self.c.t, **kw)

    def test_salutes_at_once_when_asked_and_calm(self):
        self.holo.salute(self.c.t)
        self.run_for(0.3)
        self.assertEqual(self.holo.clip, "salute")
        self.assertGreater(self.holo.clip_mix, 0.5)
        self.holo.render(self.c.t)

    def test_waits_while_she_is_talking_then_goes(self):
        self.holo.speech_started("Welcome back commander", self.c.t)
        self.holo.salute(self.c.t)
        self.run_for(1.0)
        self.assertIsNone(self.holo.clip)
        self.holo.speech_finished(self.c.t)
        self.run_for(0.5)
        self.assertEqual(self.holo.clip, "salute")

    def test_dropped_if_she_never_gets_a_calm_moment(self):
        self.holo.speech_started("A very long story", self.c.t)
        self.holo.salute(self.c.t)
        self.run_for(10.0)
        self.assertIsNone(self.holo.salute_at)
        self.holo.speech_finished(self.c.t)
        self.run_for(1.0)
        self.assertIsNone(self.holo.clip)

    def test_delay_after_the_game_loads(self):
        self.holo.salute(self.c.t, delay=12.0)
        self.run_for(5.0)
        self.assertIsNone(self.holo.clip)
        self.run_for(8.0)
        self.assertEqual(self.holo.clip, "salute")

    def test_poses_off_means_no_salute(self):
        self.holo.poses_on = False
        self.holo.salute(self.c.t)
        self.run_for(1.0)
        self.assertIsNone(self.holo.clip)

    def test_the_words_that_make_her_salute(self):
        from ui.hologram_window import SALUTE_WORDS
        for text in ("o7 commander", "Starling, oh seven", "give me a salute", "O7"):
            self.assertTrue(SALUTE_WORDS.search(text), text)
        for text in ("plot a route", "dock at station 7", "open the map"):
            self.assertFalse(SALUTE_WORDS.search(text), text)


class SaluteWithSpeech(unittest.TestCase):
    def setUp(self):
        h.clear_clips()
        self.holo, self.c = make()
        self.holo.power = 1.0
        h.get_clip(self.holo.assets, "salute", wait=True)
        self.addCleanup(h.clear_clips)

    def run_for(self, seconds):
        for _ in range(int(seconds / 0.05)):
            self.c.t += 0.05
            self.holo.tick(now=self.c.t)

    def test_saying_o7_makes_her_salute_while_she_talks(self):
        self.holo.speech_started("o7, Nyx.", self.c.t)
        self.holo.track = [(0.0, 3.0, "oh")]
        self.holo.exact_track = True
        self.run_for(0.6)
        self.assertTrue(self.holo.speaking)
        self.assertEqual(self.holo.clip, "salute")            # not cut off by her speaking
        self.assertGreater(self.holo.weights["oh"], 0.3)       # and her lips still move
        self.holo.render(self.c.t)

    def test_other_ways_of_writing_it(self):
        for line in ("Salute received. o7, Ann.", "oh seven Commander Ann", "Hi O7 everyone"):
            h.clear_clips()
            h.get_clip(self.holo.assets, "salute", wait=True)
            holo, c = make()
            holo.power = 1.0
            holo.speech_started(line, c.t)
            for _ in range(10):
                c.t += 0.05
                holo.tick(now=c.t)
            self.assertEqual(holo.clip, "salute", line)

    def test_lines_without_o7_do_not_salute(self):
        for line in ("Docking granted, pad 7.", "Go7 now", "Fly safe, Commander."):
            holo, c = make()
            holo.power = 1.0
            holo.speech_started(line, c.t)
            for _ in range(10):
                c.t += 0.05
                holo.tick(now=c.t)
            self.assertIsNone(holo.clip, line)

    def test_two_o7s_close_together_give_one_salute(self):
        self.holo.speech_started("o7, Ann.", self.c.t)
        self.run_for(0.3)
        started = self.holo.clip_start
        self.holo.speech_started("o7, Bob.", self.c.t)
        self.run_for(0.3)
        self.assertEqual(self.holo.clip_start, started)

    def test_the_salute_ends_by_itself_while_she_goes_on_talking(self):
        self.holo.speech_started("o7, Nyx.", self.c.t)
        self.holo.track = [(0.0, 30.0, "ah")]
        self.holo.exact_track = True
        self.run_for(8.0)
        self.assertIsNone(self.holo.clip)

    def test_poses_off_means_no_salute_from_speech(self):
        self.holo.poses_on = False
        self.holo.speech_started("o7, Nyx.", self.c.t)
        self.run_for(0.5)
        self.assertIsNone(self.holo.clip)


class WideWindowForTheArm(unittest.TestCase):
    def test_window_is_wider_than_her_picture_and_she_is_in_the_middle_part(self):
        holo, c = make()
        a = holo.assets
        self.assertGreater(a.pad_left, a.width * 0.4)
        self.assertEqual(a.window_w, a.width + a.pad_left + a.pad_right)
        self.assertIn("salute", a.wide_clips)
        frame = holo.render(c.t)
        self.assertEqual(frame.shape, (a.window_h, a.window_w, 3))

    def test_nothing_is_drawn_in_the_side_room_when_no_clip_is_playing(self):
        holo, c = make()
        holo.power = 1.0
        frame = np.asarray(holo.render(c.t))
        a = holo.assets
        side = frame[:, :a.pad_left - 8]
        self.assertTrue((side == np.array(h.KEY, dtype=np.uint8)).all())

    def test_the_salute_arm_is_drawn_in_the_side_room(self):
        h.clear_clips()
        holo, c = make()
        holo.power = 1.0
        holo.flicker_on = False
        h.get_clip(holo.assets, "salute", wait=True)
        holo.salute(c.t)
        seen = False
        for _ in range(80):
            c.t += 0.05
            holo.tick(now=c.t)
            frame = np.asarray(holo.render(c.t))
            side = frame[:, :holo.assets.pad_left]
            if (side.max(axis=2) > 60).sum() > 200:
                seen = True
        self.assertTrue(seen)
        h.clear_clips()

    def test_geometry_helpers_still_agree(self):
        x, y = h.window_position(1920, 1080, 200, 300, 6.5, 24)
        left, bottom = h.percents_from_position(1920, 1080, 200, 300, x, y)
        self.assertAlmostEqual(left, 6.5, delta=0.1)


class Gestures(unittest.TestCase):
    def setUp(self):
        self.holo, self.c = make()
        self.holo.power = 1.0
        self.holo.idle_on = False

    def run_for(self, seconds, step=0.05):
        for _ in range(int(seconds / step)):
            self.c.t += step
            self.holo.tick(now=self.c.t)

    def test_every_gesture_draws_and_finishes(self):
        for name in h.GESTURES:
            holo, c = make()
            holo.power = 1.0
            self.assertTrue(holo.gesture(name, c.t), name)
            for _ in range(int((h.GESTURES[name] + 0.3) / 0.05)):
                c.t += 0.05
                holo.tick(now=c.t)
                self.assertEqual(holo.render(c.t).shape[0], holo.assets.window_h)
            self.assertIsNone(holo.g_name, name)

    def test_nod_moves_the_head_down_and_back(self):
        self.holo.gesture("nod", self.c.t)
        values = []
        for _ in range(22):
            self.c.t += 0.05
            values.append(self.holo._gesture_values(self.c.t)[1])
        self.assertGreater(max(values), 0.012)
        self.assertAlmostEqual(values[-1], 0.0, delta=0.002)

    def test_shake_turns_both_ways(self):
        self.holo.gesture("shake", self.c.t)
        turns = []
        for _ in range(24):
            self.c.t += 0.05
            turns.append(self.holo._gesture_values(self.c.t)[2])
        self.assertGreater(max(turns), 0.5)
        self.assertLess(min(turns), -0.5)

    def test_glances_go_opposite_ways(self):
        self.holo.gesture("glance_left", self.c.t)
        self.c.t += 1.0
        self.assertLess(self.holo._gesture_values(self.c.t)[2], -0.5)
        self.run_for(6.0)
        self.assertTrue(self.holo.gesture("glance_right", self.c.t))
        self.c.t += 1.0
        self.assertGreater(self.holo._gesture_values(self.c.t)[2], 0.5)

    def test_startle_flashes_then_calms(self):
        self.holo.gesture("startle", self.c.t)
        self.c.t += 0.05
        self.assertGreater(self.holo._gesture_values(self.c.t)[4], 0.3)
        self.c.t += 1.0
        self.assertEqual(self.holo._gesture_values(self.c.t)[4], 0.0)

    def test_busy_or_too_soon_or_off_means_no(self):
        self.assertTrue(self.holo.gesture("nod", self.c.t))
        self.assertFalse(self.holo.gesture("tilt", self.c.t + 0.1))          # still nodding
        self.assertTrue(self.holo.gesture("startle", self.c.t + 0.1))        # a startle always may
        self.holo.poses_on = False
        self.assertFalse(self.holo.gesture("nod", self.c.t + 100))
        self.holo.poses_on = True
        self.holo.power = 0.3
        self.assertFalse(self.holo.gesture("nod", self.c.t + 100))

    def test_gesture_works_without_the_fake_3d_turn(self):
        self.holo.fx_turn = False
        self.holo.gesture("shake", self.c.t)
        for _ in range(10):
            self.c.t += 0.05
            self.holo.tick(now=self.c.t)
            self.holo.render(self.c.t)


class Reactions(unittest.TestCase):
    def setUp(self):
        h.clear_clips()
        self.holo, self.c = make()
        self.holo.power = 1.0
        self.addCleanup(h.clear_clips)

        class Sure(random.Random):
            def random(self): return 0.0
        self.holo.rng = Sure()

    def test_every_reaction_names_something_she_can_do(self):
        for event, (kind, chance) in h.REACTIONS.items():
            self.assertTrue(kind in h.GESTURES or kind in ("glance", "salute") + h.CLIP_REACTIONS or kind in h.REACTION_GROUPS, event)
            self.assertTrue(0 < chance <= 1, event)

    def test_docking_granted_nods_and_denied_shakes_the_head(self):
        self.assertTrue(self.holo.react_to("DockingGranted", self.c.t))
        self.assertEqual(self.holo.pose_wanted[0] if "nod" in self.holo.assets.clips else self.holo.g_name, "nod")   # a recorded clip beats the built-in movement
        self.holo.pose_wanted = None
        self.c.t += 5
        self.holo.g_name = None
        self.holo.g_last = -1e9
        self.assertTrue(self.holo.react_to("DockingDenied", self.c.t + 20))
        if "shake" in self.holo.assets.clips:                 # a recorded shake clip beats the built-in movement
            self.assertEqual(self.holo.pose_wanted[0], "shake")
        else:
            self.assertEqual(self.holo.g_name, "shake")

    def test_attack_startles_even_just_after_another_reaction(self):
        self.holo.react_to("DockingGranted", self.c.t)
        self.assertTrue(self.holo.react_to("Interdicted", self.c.t + 6.0))
        self.assertTrue(self.holo.g_name == "startle" or self.holo.clip == "startle")          # the recorded clip once it is loaded, the built-in jump before that

    def test_reactions_are_spaced_out(self):
        self.assertTrue(self.holo.react_to("DockingGranted", self.c.t))
        self.holo.g_name = None
        self.assertFalse(self.holo.react_to("DockingDenied", self.c.t + 2.0))

    def test_message_makes_her_glance_sideways(self):
        self.assertTrue(self.holo.react_to("ReceiveText", self.c.t))
        got = self.holo.pose_wanted[0] if self.holo.pose_wanted else self.holo.g_name        # a recorded clip beats the built-in movement
        self.assertIn(got, ("glance_left", "glance_right"))

    def test_chance_is_respected(self):
        class Never(random.Random):
            def random(self): return 0.99
        self.holo.rng = Never()
        self.assertFalse(self.holo.react_to("DockingDenied", self.c.t))

    def test_mission_done_asks_for_the_pleased_clip(self):
        self.assertTrue(self.holo.react_to("MissionCompleted", self.c.t))
        self.assertEqual(self.holo.pose_wanted[0], "pleased")
        h.get_clip(self.holo.assets, "pleased", wait=True)
        seen = set()
        for _ in range(60):
            self.c.t += 0.1
            self.holo.tick(now=self.c.t)
            seen.add(self.holo.clip)
        self.assertIn("pleased", seen)

    def test_game_closing_salutes(self):
        h.get_clip(self.holo.assets, "salute", wait=True)
        self.assertTrue(self.holo.react_to("Shutdown", self.c.t))
        for _ in range(10):
            self.c.t += 0.05
            self.holo.tick(now=self.c.t)
        self.assertEqual(self.holo.clip, "salute")

    def test_unknown_events_and_switched_off_do_nothing(self):
        self.assertFalse(self.holo.react_to("FSDJump", self.c.t))
        self.holo.poses_on = False
        self.assertFalse(self.holo.react_to("DockingGranted", self.c.t))

    def test_every_reaction_event_is_a_real_event(self):
        import json
        known = set(json.load(open("config/events.json", encoding="utf-8"))["events"])
        known |= {"Shutdown", "ReceiveText"}
        for event in h.REACTIONS:
            self.assertIn(event, known, event)



class VoidCompassGuardTests(unittest.TestCase):
    """She stays above Void Compass's overlay, but only when she is showing, Void Compass is connected and the setting is on."""

    def test_guard_needs_all_three(self):
        from ui.hologram_window import should_guard
        self.assertTrue(should_guard(True, True, True))
        self.assertFalse(should_guard(False, True, True))
        self.assertFalse(should_guard(True, False, True))
        self.assertFalse(should_guard(True, True, False))

    def test_raising_does_nothing_off_windows(self):
        from ui.hologram_window import raise_if_covered
        self.assertFalse(raise_if_covered(object()))

    def test_setting_is_on_by_default_and_on_the_overlays_page(self):
        from core.settings import DEFAULTS
        from ui.settings_model import build_pages
        self.assertTrue(DEFAULTS["hologram"]["above_void_compass"])
        keys = [f.key for p in build_pages() if p.id == "overlays" for f in p.fields]
        self.assertIn("hologram.above_void_compass", keys)

    def test_the_feed_asks_the_watcher(self):
        from ui.hologram_window import HologramFeed

        class Watcher:
            def void_compass_running(self):
                return True

        class App:
            watcher = Watcher()
        self.assertTrue(HologramFeed.void_running(type("F", (), {"app": App()})()))
        self.assertFalse(HologramFeed.void_running(type("F", (), {"app": object()})()))
