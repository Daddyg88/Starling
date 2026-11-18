import unittest

from ui import game_watch as gw


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class State:
    game_quit = False


class Watch(unittest.TestCase):
    def setUp(self):
        gw.set_closed(False)
        self.clock = Clock()
        self.state = State()
        self.titles = ["Elite - Dangerous (CLIENT)", "Discord"]
        self.watch = gw.GameWatch(lambda: self.state, lambda: self.titles, self.clock, absent_seconds=8)

    def tearDown(self):
        gw.set_closed(False)

    def test_game_window_there_means_open(self):
        self.clock.t += 50
        self.assertFalse(self.watch.poll())
        self.assertFalse(gw.game_closed())

    def test_goes_when_the_window_has_been_gone_a_while(self):
        self.titles = ["Discord"]
        self.clock.t += 3
        self.assertFalse(self.watch.poll())                 # a short gap (a screen mode change) is ignored
        self.clock.t += 6
        self.assertTrue(self.watch.poll())
        self.assertTrue(gw.game_closed())
        self.assertTrue(self.state.game_quit)               # the route map and biology panel hide too

    def test_comes_back_when_the_game_returns(self):
        self.titles = []
        self.clock.t += 20
        self.assertTrue(self.watch.poll())
        self.titles = ["Elite - Dangerous (CLIENT)"]
        self.clock.t += 1
        self.assertFalse(self.watch.poll())
        self.assertFalse(gw.game_closed())

    def test_the_launcher_is_not_the_game(self):
        self.titles = ["Elite Dangerous Launcher"]
        self.clock.t += 20
        self.assertTrue(self.watch.poll())

    def test_unreadable_window_list_changes_nothing(self):
        self.watch.lister = lambda: None
        self.clock.t += 100
        self.assertFalse(self.watch.poll())
        self.assertFalse(self.state.game_quit)

    def test_a_failing_lister_is_harmless(self):
        def broken():
            raise RuntimeError("no")
        self.watch.lister = broken
        self.clock.t += 100
        self.assertFalse(self.watch.poll())

    def test_overlays_check_the_flag(self):
        import inspect
        from ui import hack_overlay, red_alert_overlay, settlement_overlay, hologram_window
        for module in (hack_overlay, red_alert_overlay, settlement_overlay, hologram_window):
            self.assertIn("game_watch.game_closed()", inspect.getsource(module), module.__name__)


if __name__ == "__main__":
    unittest.main()
