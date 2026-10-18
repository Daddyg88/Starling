import unittest

from control.sender import game_is_active


class FakeWin:
    def __init__(self, front, game=1234, brings=True):
        self.front, self.game, self.brings, self.brought = list(front), game, brings, 0

    def foreground(self):
        return self.front[0] if len(self.front) == 1 else self.front.pop(0)

    def find_game(self):
        return self.game

    def bring_forward(self, handle):
        self.brought += 1
        if self.brings:
            self.front = [(1234, "Elite - Dangerous (CLIENT)", "EliteDangerous64.exe")]
        return True


ELITE = (1234, "Elite - Dangerous (CLIENT)", "EliteDangerous64.exe")
VOID = (55, "Void Compass", "VoidCompass.exe")
BROWSER = (77, "Some page - Chrome", "chrome.exe")


class Focus(unittest.TestCase):
    def test_elite_in_front_is_fine(self):
        win = FakeWin([ELITE])
        self.assertTrue(game_is_active(win, sleep=lambda s: None))
        self.assertEqual(win.brought, 0)

    def test_void_compass_in_front_brings_elite_forward(self):
        win = FakeWin([VOID])
        self.assertTrue(game_is_active(win, sleep=lambda s: None))
        self.assertEqual(win.brought, 1)

    def test_void_compass_in_front_but_elite_cannot_be_brought(self):
        win = FakeWin([VOID], brings=False)
        self.assertFalse(game_is_active(win, sleep=lambda s: None))

    def test_void_compass_in_front_and_no_game_running(self):
        self.assertFalse(game_is_active(FakeWin([VOID], game=0), sleep=lambda s: None))

    def test_other_windows_are_never_touched(self):
        win = FakeWin([BROWSER])
        self.assertFalse(game_is_active(win, sleep=lambda s: None))
        self.assertEqual(win.brought, 0)


if __name__ == "__main__":
    unittest.main()
