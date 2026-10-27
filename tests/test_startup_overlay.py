import os
import tempfile
import time
import unittest
from pathlib import Path

from journal.game_state import GameState
from journal.monitor import STALE_STATUS_SECONDS, hide_if_game_closed


class StartupOverlay(unittest.TestCase):
    """She starts with Elite closed: the last journal is old news, so the biology box must not appear."""

    def status_file(self, age_seconds):
        path = Path(tempfile.mkdtemp()) / "Status.json"
        path.write_text("{}", encoding="utf-8")
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def test_an_old_status_file_means_the_game_is_closed(self):
        state = GameState()
        self.assertTrue(hide_if_game_closed(self.status_file(STALE_STATUS_SECONDS + 600), state))
        self.assertTrue(state.game_quit)

    def test_a_fresh_status_file_leaves_the_overlay_alone(self):
        state = GameState()
        self.assertFalse(hide_if_game_closed(self.status_file(5), state))
        self.assertFalse(state.game_quit)

    def test_no_status_file_at_all_hides_it_too(self):
        state = GameState()
        self.assertTrue(hide_if_game_closed(Path(tempfile.mkdtemp()) / "Status.json", state))
        self.assertTrue(state.game_quit)

    def test_loading_in_shows_it_again(self):
        from tests.test_bio_overlay import run
        _, state = run([{"event": "LoadGame", "Commander": "X"}])
        state.game_quit = True
        _, state2 = run([{"event": "FSDJump", "StarSystem": "Test", "StarPos": [0, 0, 0]}])
        self.assertFalse(state2.game_quit)

    def test_missing_state_does_not_crash(self):
        self.assertFalse(hide_if_game_closed(self.status_file(5), None))
        state = GameState()
        self.assertTrue(hide_if_game_closed(None, state))        # no path: the game has not run here
        self.assertTrue(state.game_quit)


if __name__ == "__main__":
    unittest.main()
