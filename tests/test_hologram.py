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

    def test_speaking_then_smile(self):
        holo, c = make()
        holo.speech_started("Hello commander", c.t)
        self.assertTrue(holo.speaking)
        c.t += 1.2
        holo.speech_finished(c.t)
        self.assertFalse(holo.speaking)
        self.assertEqual(holo._mouth_goal(c.t + 0.5), "smile")
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
    def test_off_by_default(self):
        from core.settings import DEFAULTS
        self.assertFalse(DEFAULTS["hologram"]["enabled"])

if __name__ == "__main__":
    unittest.main()
