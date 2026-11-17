import json
import unittest

from ui.window_voice import WindowVoice, which


class Settings:
    def __init__(self, **values):
        self.values = dict(values)
        self.saved = 0

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.saved += 1


class Narrator:
    def __init__(self): self.said = []
    def say(self, key, fields=None): self.said.append(key)


class Phrases(unittest.TestCase):
    def test_chat_window(self):
        for text in ("show the chat window", "Open the chat window", "bring up the stream chat window", "show me the twitch chat window",
                     "turn on the chat window", "switch the chat window on", "please show the chat window", "display the chat feed"):
            self.assertEqual(which(text), "chat_on", text)
        for text in ("hide the chat window", "close the chat window", "turn off the chat window", "turn the chat window off",
                     "switch off the chat window", "put away the chat window", "get rid of the chat window", "close the stream chat window"):
            self.assertEqual(which(text), "chat_off", text)

    def test_memory_window(self):
        for text in ("show the memory window", "open the memory window", "show me what you know about me window", "open the knowledge window",
                     "show my memory list", "bring up the memory page"):
            self.assertEqual(which(text), "memory_on", text)
        for text in ("close the memory window", "hide the memory window", "close the knowledge window", "hide the memory list"):
            self.assertEqual(which(text), "memory_off", text)

    def test_ordinary_talk_is_left_alone(self):
        for text in ("", "chat off", "pause the chat", "chat on", "what do you remember", "what do you know about me", "show the dashboard",
                     "close the window", "show the map", "open the cargo scoop", "hide the chat from the viewers", "tell the chat window to be quiet",
                     "forget everything", "how is the chat doing"):
            self.assertIsNone(which(text), text)


class Handling(unittest.TestCase):
    def test_chat_window_is_a_setting(self):
        settings, nar, asked = Settings(**{"streaming.enabled": True}), Narrator(), []
        voice = WindowVoice(settings, asked.append, nar)
        self.assertEqual(voice.try_handle("hide the chat window"), "Chat window hidden.")
        self.assertFalse(settings.get("streaming.window"))
        self.assertEqual(voice.try_handle("show the chat window"), "Chat window shown.")
        self.assertTrue(settings.get("streaming.window"))
        self.assertEqual(nar.said, ["Window_ChatHidden", "Window_ChatShown"])
        self.assertEqual(settings.saved, 2)
        self.assertEqual(asked, [])

    def test_showing_it_while_chat_is_off_says_what_to_do(self):
        settings, nar = Settings(**{"streaming.enabled": False}), Narrator()
        reply = WindowVoice(settings, lambda n: None, nar).try_handle("show the chat window")
        self.assertIn("chat on", reply.lower())
        self.assertEqual(nar.said, ["Window_ChatNeedsChat"])
        self.assertTrue(settings.get("streaming.window"))          # it will appear as soon as chat is on

    def test_memory_window_is_handed_to_the_dashboard(self):
        asked, nar = [], Narrator()
        voice = WindowVoice(Settings(), asked.append, nar)
        voice.try_handle("open the memory window")
        voice.try_handle("close the memory window")
        self.assertEqual(asked, ["memory_window", "memory_window_close"])
        self.assertEqual(nar.said, ["Window_MemoryShown", "Window_MemoryHidden"])

    def test_not_for_us(self):
        asked = []
        self.assertIsNone(WindowVoice(Settings(), asked.append, Narrator()).try_handle("lower the landing gear"))
        self.assertEqual(asked, [])

    def test_her_lines_exist(self):
        with open("voicepacks/default/streaming.json", encoding="utf-8") as handle:
            data = json.load(handle)
        for key in ("Window_ChatShown", "Window_ChatHidden", "Window_ChatNeedsChat", "Window_MemoryShown", "Window_MemoryHidden"):
            self.assertTrue(data[key], key)


class AppRequests(unittest.TestCase):
    def test_requests_are_capped(self):
        from core.app import App
        fake = type("Fake", (), {"ui_requests": []})()
        for n in range(30):
            App.request_ui(fake, "memory_window")
        self.assertEqual(len(fake.ui_requests), 10)

    def test_the_voice_is_wired_in_the_app(self):
        import inspect
        from core.app import App
        self.assertIn("WindowVoice", inspect.getsource(App))
        from ui import dashboard
        self.assertIn("_poll_ui_requests", inspect.getsource(dashboard))


if __name__ == "__main__":
    unittest.main()
