import unittest
from types import SimpleNamespace

from control.runner import CommandRunner
from core.event_bus import EventBus
from personality.brain import Brain, load_intents
from tests.test_commands import FakeBook, FakeSpeech
from tests.test_phase6b import dialogue, make_settings


class BrainOwnsTests(unittest.TestCase):
    def runner(self):
        brain = SimpleNamespace(recognises=Brain.recognises.__get__(SimpleNamespace(intents=load_intents())),
                                try_handle=lambda text, deliberate=True: "chat")
        return CommandRunner(EventBus(), FakeSpeech(), dialogue(), make_settings(), book=FakeBook(), brain=brain)

    def test_tell_me_more_is_chat_not_the_tool_mode_key(self):
        r = self.runner()
        outcome = r.run_text("tell me more")[0]
        self.assertEqual(outcome.status, "route")
        self.assertEqual(outcome.detail, "chat")

    def test_real_commands_still_win(self):
        r = self.runner()
        for said in ("open the galaxy map", "stop", "show off"):
            outcome = r.run_text(said)[0]
            self.assertNotEqual(outcome.status, "route", said)


if __name__ == "__main__":
    unittest.main()
