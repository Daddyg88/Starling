import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.settings import Settings
from tts.base_tts import BaseTTS, VoiceSettings
from tts.mci_player import MciPlayer, PlaybackError
from tts.prerecorded_tts import PrerecordedTTS
from tts.speech_manager import SpeechManager
from tts.windows_tts import WindowsTTS, build_environment


class FakeProvider(BaseTTS):
    """Pretends to speak. Records what it was asked and can be made slow or broken."""

    def __init__(self, name, works=True, duration=0.0, is_available=True):
        self.name = name
        self.label = name
        self.works = works
        self.duration = duration
        self.is_available = is_available
        self.spoken = []
        self.stopped = threading.Event()
        self.started = threading.Event()

    def available(self):
        return (True, "") if self.is_available else (False, "off")

    def speak(self, text, voice, audio_path=None):
        self.spoken.append((text, audio_path))
        self.started.set()
        self.stopped.clear()
        if self.duration:
            self.stopped.wait(self.duration)
        return self.works

    def stop(self):
        self.stopped.set()


def make_manager(**providers):
    settings = Settings(Path(tempfile.gettempdir()) / "starling_nonexistent.json").load()
    manager = SpeechManager(providers, settings)
    manager.start()
    return manager


class VoiceSettingsTests(unittest.TestCase):
    def test_values_are_kept_in_range(self):
        s = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
        s.set("tts.volume", 500)
        s.set("tts.rate", -99)
        s.set("tts.pitch", "banana")
        v = VoiceSettings.from_settings(s)
        self.assertEqual((v.volume, v.rate, v.pitch), (100, -10, 0))


class WindowsVoiceTests(unittest.TestCase):
    def test_text_travels_in_an_environment_variable(self):
        env = build_environment('He said "hi" & left', VoiceSettings(voice="Zira", volume=80, rate=2), {})
        self.assertEqual(env["STARLING_SAY"], 'He said "hi" & left')
        self.assertEqual(env["STARLING_VOICE"], "Zira")
        self.assertEqual((env["STARLING_VOLUME"], env["STARLING_RATE"], env["STARLING_SSML"]), ("80", "2", "0"))

    def test_pitch_switches_to_ssml_and_escapes_text(self):
        env = build_environment("a < b", VoiceSettings(pitch=8), {})
        self.assertEqual(env["STARLING_SSML"], "1")
        self.assertIn("a &lt; b", env["STARLING_SAY"])
        self.assertIn('pitch="x-high"', env["STARLING_SAY"])

    def test_not_available_off_windows(self):
        import sys
        if sys.platform != "win32":
            self.assertFalse(WindowsTTS().available()[0])
            self.assertFalse(WindowsTTS().speak("hello", VoiceSettings()))


class MciPlayerTests(unittest.TestCase):
    def make_send(self, modes, fail_open=False):
        calls = []
        modes = list(modes)

        def send(command):
            calls.append(command)
            if command.startswith("open") and fail_open:
                return 266, "bad file"
            if command.startswith("status"):
                return 0, (modes.pop(0) if modes else "stopped")
            return 0, ""
        return send, calls

    def test_plays_until_the_file_ends_then_cleans_up(self):
        send, calls = self.make_send(["playing", "playing", "stopped"])
        MciPlayer(send).play("C:\\x\\y.mp3", 50)
        self.assertTrue(calls[0].startswith('open "C:\\x\\y.mp3" type mpegvideo alias'))
        self.assertIn("setaudio starling1 volume to 500", calls)
        self.assertEqual(calls[-2:], ["stop starling1", "close starling1"])

    def test_stop_cuts_playback_short(self):
        send, calls = self.make_send(["playing"] * 1000)
        player = MciPlayer(send)
        threading.Timer(0.2, player.stop).start()
        started = time.monotonic()
        player.play("a.mp3")
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(calls[-1], "close starling1")

    def test_open_failure_raises(self):
        send, _ = self.make_send([], fail_open=True)
        with self.assertRaises(PlaybackError):
            MciPlayer(send).play("a.mp3")

    def test_prerecorded_provider_reports_failure_instead_of_crashing(self):
        send, _ = self.make_send([], fail_open=True)
        provider = PrerecordedTTS(MciPlayer(send))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.mp3"
            path.write_bytes(b"x")
            with self.assertLogs("starling.recorded", level="WARNING"):
                self.assertFalse(provider.speak("", VoiceSettings(), path))

    def test_missing_file_is_not_a_crash(self):
        send, _ = self.make_send([])
        self.assertFalse(PrerecordedTTS(MciPlayer(send)).speak("", VoiceSettings(), Path("nope.mp3")))


class SpeechManagerTests(unittest.TestCase):
    def tearDown(self):
        getattr(self, "manager", None) and self.manager.stop()

    def test_recorded_line_is_played_and_text_is_not_spoken(self):
        rec, win = FakeProvider("recorded"), FakeProvider("kokoro")
        self.manager = make_manager(recorded=rec, kokoro=win)
        self.manager.say(text="Roger.", audio_path=Path("roger.mp3"))
        self.assertTrue(self.manager.wait_until_idle(3))
        self.assertEqual(len(rec.spoken), 1)
        self.assertEqual(win.spoken, [])

    def test_failed_recording_falls_back_to_the_windows_voice(self):
        rec, win = FakeProvider("recorded", works=False), FakeProvider("kokoro")
        self.manager = make_manager(recorded=rec, kokoro=win)
        with self.assertLogs("starling.speech", level="WARNING"):
            self.manager.say(text="Roger.", audio_path=Path("roger.mp3"))
            self.assertTrue(self.manager.wait_until_idle(3))
        self.assertEqual([t for t, _ in win.spoken], ["Roger."])

    def test_then_speak_plays_recording_then_text(self):
        rec, win = FakeProvider("recorded"), FakeProvider("kokoro")
        self.manager = make_manager(recorded=rec, kokoro=win)
        self.manager.say(text="Fuel is low.", audio_path=Path("warning.mp3"), speak_text_after=True, priority="critical")
        self.assertTrue(self.manager.wait_until_idle(3))
        self.assertEqual(len(rec.spoken), 1)
        self.assertEqual([t for t, _ in win.spoken], ["Fuel is low."])

    def test_after_text_is_spoken_after_the_recording(self):
        rec, win = FakeProvider("recorded"), FakeProvider("kokoro")
        self.manager = make_manager(recorded=rec, kokoro=win)
        self.manager.say(text="Sample collected: Bacterium.", audio_path=Path("s.mp3"), after_text="Bacterium")
        self.assertTrue(self.manager.wait_until_idle(3))
        self.assertEqual([t for t, _ in win.spoken], ["Bacterium"])

    def test_text_is_spoken_in_full_when_there_is_no_recording(self):
        win = FakeProvider("kokoro")
        self.manager = make_manager(kokoro=win)
        self.manager.say(text="Sample collected: Bacterium.", after_text="Bacterium")
        self.assertTrue(self.manager.wait_until_idle(3))
        self.assertEqual([t for t, _ in win.spoken], ["Sample collected: Bacterium."])

    def test_no_voice_available_does_not_crash(self):
        win = FakeProvider("kokoro", is_available=False)
        self.manager = make_manager(kokoro=win)
        with self.assertLogs("starling.speech", level="ERROR"):
            self.manager.say(text="Hello.")
            self.assertTrue(self.manager.wait_until_idle(3))

    def test_critical_cuts_off_ordinary_speech_and_goes_first(self):
        win = FakeProvider("kokoro", duration=5)
        self.manager = make_manager(kokoro=win)
        self.manager.say(text="Ordinary news.", priority="normal")
        self.assertTrue(win.started.wait(2))
        self.manager.say(text="Hull breach!", priority="critical")
        deadline = time.monotonic() + 3
        while len(win.spoken) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual([t for t, _ in win.spoken], ["Ordinary news.", "Hull breach!"])

    def test_low_priority_is_dropped_while_busy(self):
        win = FakeProvider("kokoro", duration=0.5)
        self.manager = make_manager(kokoro=win)
        self.manager.say(text="First.", priority="normal")
        self.assertTrue(win.started.wait(2))
        self.assertFalse(self.manager.say(text="Chatter.", priority="low"))

    def test_critical_is_never_dropped_for_age(self):
        win = FakeProvider("kokoro")
        settings = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
        now = [0.0]
        manager = SpeechManager({"kokoro": win}, settings, clock=lambda: now[0])
        manager._running = True          # queue without a thread so we control timing
        manager.say(text="Old normal.", priority="normal")
        manager.say(text="Old critical.", priority="critical")  # clears the waiting normal line
        now[0] = 100.0
        manager._running = False
        manager.start()
        self.assertTrue(manager.wait_until_idle(3))
        manager.stop()
        self.assertEqual([t for t, _ in win.spoken], ["Old critical."])

    def test_stale_ordinary_lines_are_dropped(self):
        win = FakeProvider("kokoro")
        settings = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
        now = [0.0]
        manager = SpeechManager({"kokoro": win}, settings, clock=lambda: now[0])
        manager._running = True
        manager.say(text="Old news.", priority="normal")
        now[0] = 100.0
        manager.start()
        self.assertTrue(manager.wait_until_idle(3))
        manager.stop()
        self.assertEqual(win.spoken, [])

    def test_queue_stays_short(self):
        win = FakeProvider("kokoro", duration=1.0)
        self.manager = make_manager(kokoro=win)
        self.manager.say(text="Now speaking.")
        self.assertTrue(win.started.wait(2))
        for i in range(8):
            self.manager.say(text="Line %d." % i)
        self.assertGreaterEqual(self.manager.dropped, 5)

    def test_stop_ends_the_thread_quickly(self):
        win = FakeProvider("kokoro", duration=30)
        manager = make_manager(kokoro=win)
        manager.say(text="A very long sentence.")
        self.assertTrue(win.started.wait(2))
        started = time.monotonic()
        manager.stop()
        self.assertLess(time.monotonic() - started, 4)


if __name__ == "__main__":
    unittest.main()
