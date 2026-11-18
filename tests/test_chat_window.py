import unittest

from streaming import chat
from streaming.bridge import ChatBridge
from streaming.events import StreamEvent
from streaming.feed import ChatFeed, describe_event
from ui import chat_window as cw


class Settings:
    def __init__(self, **values):
        self.values = {"streaming." + k: v for k, v in values.items()}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        pass


def message(text, user="Ann", platform="twitch", **kw):
    return chat.ChatMessage(platform, user, text, **kw)


class Feed(unittest.TestCase):
    def test_lines_come_back_in_order_and_only_once(self):
        feed = ChatFeed(clock=lambda: 5.0)
        feed.add_message(message("hello there"))
        feed.add_message(message("hi from youtube", "Bob", "youtube"))
        lines = feed.since(0)
        self.assertEqual([l.seq for l in lines], [1, 2])
        self.assertEqual([l.platform for l in lines], ["twitch", "youtube"])
        self.assertEqual(feed.since(2), [])
        feed.add_message(message("third"))
        self.assertEqual([l.text for l in feed.since(2)], ["third"])

    def test_messages_are_cleaned_and_empty_ones_ignored(self):
        feed = ChatFeed()
        feed.add_message(message("   "))
        feed.add_message(message("nice \U0001F600 landing\x00 :D", "A<b>n n!"))
        line = feed.since(0)[0]
        self.assertEqual(line.text, "nice landing")
        self.assertEqual(line.user, "Abn n")
        feed.add_message(message("x" * 1000))
        self.assertEqual(len(feed.since(0)[-1].text), 300)

    def test_keeps_only_the_newest(self):
        feed = ChatFeed(max_lines=5)
        for n in range(12):
            feed.add_message(message("line %d" % n))
        self.assertEqual([l.text for l in feed.since(0)], ["line %d" % n for n in range(7, 12)])
        self.assertEqual(feed.last_seq(), 12)

    def test_badges_are_kept(self):
        feed = ChatFeed()
        feed.add_message(message("hi", mod=True, sub=True))
        line = feed.since(0)[0]
        self.assertEqual(cw.name_badges(line), ["mod", "sub"])

    def test_event_lines(self):
        self.assertEqual(describe_event(StreamEvent("sub", "Ann", 0, "twitch")), "Ann subscribed")
        self.assertEqual(describe_event(StreamEvent("resub", "Ann", 6, "twitch")), "Ann resubscribed (6 months)")
        self.assertEqual(describe_event(StreamEvent("gift", "Bob", 5, "twitch")), "Bob gifted 5 subs")
        self.assertEqual(describe_event(StreamEvent("gift", "Bob", 1, "twitch")), "Bob gifted 1 sub")
        self.assertEqual(describe_event(StreamEvent("raid", "Cy", 30, "twitch")), "Raid from Cy: 30 viewers")
        self.assertEqual(describe_event(StreamEvent("tip", "Di", 0, "youtube")), "Di sent a Super Chat")
        self.assertEqual(describe_event(StreamEvent("chat_messages", "", 100)), "")
        feed = ChatFeed()
        self.assertIsNone(feed.add_event(StreamEvent("chat_messages", "", 100)))
        feed.add_event(StreamEvent("raid", "Cy", 30, "twitch"))
        self.assertEqual(feed.since(0)[0].kind, "event")


class BridgeFeed(unittest.TestCase):
    def test_every_message_reaches_the_feed_even_when_the_work_queue_is_full(self):
        class Director:
            log = []
        bridge = ChatBridge(Settings(enabled=True), Director())
        for n in range(60):                      # far more than the work queue holds (and nothing is processing it)
            bridge.submit(message("message %d" % n, "User%d" % n, "youtube" if n % 2 else "twitch"))
        bridge.submit(StreamEvent("sub", "Zed", 0, "twitch"))
        lines = bridge.feed.since(0)
        self.assertEqual(len(lines), 61)
        self.assertEqual({l.platform for l in lines}, {"twitch", "youtube"})
        self.assertEqual(lines[-1].kind, "event")


class Helpers(unittest.TestCase):
    def test_pieces_for_a_chat_line_and_an_event(self):
        feed = ChatFeed(clock=lambda: 0.0)
        feed.add_message(message("o7 everyone", "Ann", "youtube", mod=True))
        feed.add_event(StreamEvent("sub", "Bob", 0, "twitch"))
        chat_line, event_line = feed.since(0)
        tags = [t for t, _ in cw.pieces(chat_line)]
        self.assertEqual(tags, ["time", "p_youtube", "name_youtube", "badge_mod", "text"])
        text = "".join(p for _t, p in cw.pieces(chat_line, show_time=False))
        self.assertEqual(text, "\u25CF Ann [mod]: o7 everyone")
        self.assertEqual([t for t, _ in cw.pieces(event_line, show_time=False)], ["p_twitch", "event"])

    def test_font_sizes(self):
        self.assertEqual(cw.font_size("14"), 14)
        self.assertEqual(cw.font_size(99), 12)
        self.assertEqual(cw.font_size(None), 12)
        self.assertEqual(cw.step_font(12, 1), 14)
        self.assertEqual(cw.step_font(10, -1), 10)
        self.assertEqual(cw.step_font(18, 1), 18)

    def test_start_geometry(self):
        screen = (0, 0, 1920, 1080)
        self.assertEqual(cw.start_geometry("", screen), "380x520+1516+70")           # top right by default
        self.assertEqual(cw.start_geometry("500x400+100+100", screen), "500x400+100+100")
        self.assertEqual(cw.start_geometry("500x400+5000+100", screen), "380x520+1516+70")   # that monitor is gone
        self.assertEqual(cw.start_geometry("100x50+100+100", screen), "380x520+1516+70")     # too small to be real
        self.assertEqual(cw.start_geometry("garbage", (0, 0, 300, 300)), "300x300+0+70")

    def test_resize_never_below_the_minimum_or_off_the_screen(self):
        self.assertEqual(cw.resized(400, 500, -1000, -1000), cw.MIN_SIZE)
        self.assertEqual(cw.resized(400, 500, 50, 20), (450, 520))
        self.assertEqual(cw.resized(400, 500, 5000, 5000, (1920, 1080)), (1920, 1080))

    def test_when_it_is_wanted(self):
        bridge = object()
        self.assertTrue(cw.wanted(Settings(enabled=True), bridge))                   # the switch is on by default
        self.assertFalse(cw.wanted(Settings(enabled=True, window=False), bridge))
        self.assertFalse(cw.wanted(Settings(enabled=False), bridge))
        self.assertFalse(cw.wanted(Settings(enabled=True), None))

    def test_stamp(self):
        self.assertRegex(cw.stamp(1700000000), r"^\d\d:\d\d$")
        self.assertEqual(cw.stamp("x"), "")


class FakeRoot:
    def __init__(self): self.jobs = []
    def after(self, ms, fn): self.jobs.append((ms, fn))


class Loop(unittest.TestCase):
    """The tkinter parts are not run here (no screen); the decisions in the loop are."""

    def make(self, settings, bridge):
        window = cw.ChatWindow(FakeRoot(), settings, lambda: bridge)
        built, closed = [], []
        window._build = lambda: (built.append(1), setattr(window, "window", object()))
        window._refresh = lambda b: None
        window._close_window = lambda: (closed.append(1), setattr(window, "window", None))
        return window, built, closed

    def test_opens_when_wanted_and_closes_when_not(self):
        settings = Settings(enabled=True)
        window, built, closed = self.make(settings, object())
        window._tick()
        window._tick()
        self.assertEqual(len(built), 1)                       # built once, not every tick
        settings.set("streaming.window", False)
        window._tick()
        self.assertEqual(len(closed), 1)
        window._tick()
        self.assertEqual(len(closed), 1)

    def test_a_failure_switches_it_off_for_the_session_without_raising(self):
        window, built, closed = self.make(Settings(enabled=True), object())
        window._build = lambda: (_ for _ in ()).throw(RuntimeError("no screen"))
        window._tick()
        self.assertTrue(window._broken)
        window._tick()
        self.assertEqual(len(window.root.jobs), 3)            # it keeps its timer going, quietly

    def test_pieces_exist_for_the_settings(self):
        from core.settings import DEFAULTS
        for name in ("window", "window_pin", "window_font", "window_geometry"):
            self.assertIn(name, DEFAULTS["streaming"])


if __name__ == "__main__":
    unittest.main()
