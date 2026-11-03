import json
import unittest

from control.matcher import Matcher
from journal.game_state import GameState
from streaming import chat, twitch
from streaming.bridge import ChatBridge
from streaming.voice import StreamChatVoice


class Settings:
    def __init__(self, **values):
        self.values = {"streaming." + k: v for k, v in values.items()}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        pass


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


def ship_state(**flags):
    state = GameState()
    bits = 1 << chat.IN_MAIN_SHIP
    for name in flags:
        bits |= 1 << getattr(chat, name)
    state.status_flags = bits
    return state


def make(state=None, **settings):
    base = {"enabled": True}
    base.update(settings)
    clock = Clock()
    done, asked, said = [], [], []
    director = chat.ChatDirector(Settings(**base), lambda: state if state is not None else ship_state(),
                                 lambda a: done.append(a.key) or True, lambda u, q: asked.append((u, q)) or True,
                                 lambda key, fields=None: said.append((key, fields)), clock)
    return director, clock, done, asked, said


def msg(text, user="Gav", **kw):
    return chat.ChatMessage("twitch", user, text, **kw)


class Parsing(unittest.TestCase):
    def test_parse(self):
        cases = {"!lights": ("action", "lights"), "!starling lights": ("action", "lights"), "!Night": ("action", "night_vision"),
                 "!starling night vision": ("action", "night_vision"), "!starling what is a neutron star?": ("ask", "what is a neutron star?"),
                 "!starling, are you single": ("ask", "are you single"), "hello": None, "!starling": None, "!unknown": None,
                 "!lights now please everyone": None, "  !LIGHTS ": ("action", "lights")}
        for text, expected in cases.items():
            self.assertEqual(chat.parse(text), expected, text)

    def test_custom_prefix(self):
        self.assertEqual(chat.parse("!ship hi there", "!ship"), ("ask", "hi there"))
        self.assertIsNone(chat.parse("!starling hi", "!ship"))

    def test_names_and_words(self):
        self.assertEqual(chat.clean_name("Gav<script>!"), "Gavscript")
        self.assertEqual(chat.clean_name(""), "someone")
        self.assertTrue(chat.has_blocked_word("you are a Banana!", ["banana"]))
        self.assertFalse(chat.has_blocked_word("bananas", ["banana"]))
        self.assertEqual(chat.split_words("a, b;c\nd"), ["a", "b", "c", "d"])

    def test_action_phrases_are_real_commands(self):
        matcher = Matcher()
        expected = {"lights": "lights", "night_vision": "night_vision", "head_look": "head_look", "scoop": "scoop", "gear": "gear"}
        for action in chat.ACTIONS:
            found = matcher.match(action.phrase)
            self.assertIsNotNone(found, action.phrase)
            self.assertEqual(found.command.id, expected[action.key])
            self.assertEqual(found.intent, "toggle")


class Rules(unittest.TestCase):
    def test_off_means_ignored(self):
        director, _c, done, asked, _s = make(enabled=False)
        self.assertEqual(director.handle(msg("!lights")).status, "ignored")
        self.assertEqual(director.handle(msg("!lights"), test=True).status, "done")
        self.assertEqual(done, ["lights"])

    def test_action_and_question(self):
        director, _c, done, asked, said = make()
        self.assertEqual(director.handle(msg("!lights")).status, "done")
        self.assertEqual(said[0][0], "StreamChat_Action")
        self.assertEqual(director.handle(msg("!starling why is the sky blue", user="Bob")).status, "answered")
        self.assertEqual(asked, [("Bob", "why is the sky blue")])

    def test_who_may_use_it(self):
        director, *_ = make(who="mods")
        self.assertEqual(director.handle(msg("!lights")).status, "blocked")
        self.assertEqual(director.handle(msg("!lights", user="M", mod=True)).status, "done")
        director, clock, *_ = make(who="subscribers")
        self.assertEqual(director.handle(msg("!lights")).status, "blocked")
        self.assertEqual(director.handle(msg("!lights", sub=True)).status, "done")
        clock.now += 30
        self.assertEqual(director.handle(msg("!lights", user="Owner", owner=True)).status, "done")

    def test_blocked_things(self):
        director, _c, _d, asked, _s = make(blocked_words="banana, rude")
        self.assertEqual(director.handle(msg("!starling you banana")).note, "blocked word")
        self.assertEqual(director.handle(msg("!starling look at www.evil.com")).note, "link")
        self.assertEqual(director.handle(msg("!starling " + "x" * 200)).note, "too long")
        self.assertEqual(asked, [])
        director, *_ = make(ask_enabled=False)
        self.assertEqual(director.handle(msg("!starling hi")).note, "questions are off")

    def test_actions_must_be_switched_on(self):
        director, _c, done, *_ = make()
        self.assertEqual(director.handle(msg("!gear")).note, "that action is off")
        self.assertEqual(director.handle(msg("!headlook", user="B")).note, "that action is off")
        self.assertEqual(done, [])

    def test_cooldowns(self):
        director, clock, done, *_ = make(user_cooldown=45, action_cooldown=20)
        self.assertEqual(director.handle(msg("!lights", user="A")).status, "done")
        self.assertEqual(director.handle(msg("!lights", user="A")).status, "cooldown")      # same viewer
        self.assertEqual(director.handle(msg("!nightvision", user="B")).status, "cooldown")   # anyone, too soon after the last action
        clock.now += 21
        self.assertEqual(director.handle(msg("!nightvision", user="B")).status, "done")
        clock.now += 30
        self.assertEqual(director.handle(msg("!lights", user="A")).status, "done")           # A's 45 seconds are over
        self.assertEqual(done, ["lights", "night_vision", "lights"])

    def test_streamer_has_no_viewer_cooldown(self):
        director, clock, done, *_ = make(action_cooldown=5)
        director.handle(msg("!lights", user="Me", owner=True))
        clock.now += 6
        self.assertEqual(director.handle(msg("!lights", user="Me", owner=True)).status, "done")

    def test_safety_checks(self):
        quit_state = ship_state()
        quit_state.game_quit = True
        director, *_ = make(state=quit_state)
        self.assertEqual(director.handle(msg("!lights")).status, "refused")
        menu = ship_state()
        menu.gui_focus = 6
        director, *_ = make(state=menu)
        self.assertEqual(director.handle(msg("!lights")).note, "a menu is open")
        director, *_ = make(state=GameState())                  # not in the ship
        self.assertEqual(director.handle(msg("!lights")).note, "not in the ship")

    def test_gear_is_extra_careful(self):
        for flag, reason in (("DOCKED", "docked or landed"), ("LANDED", "docked or landed"), ("SUPERCRUISE", "in supercruise"),
                             ("MASS_LOCKED", "too close to something big"), ("LAT_LONG", "too close to something big"),
                             ("IN_DANGER", "in danger")):
            director, _c, done, _a, said = make(state=ship_state(**{flag: True}), act_gear=True)
            result = director.handle(msg("!gear"))
            self.assertEqual((result.status, result.note), ("refused", reason), flag)
            self.assertEqual(said[-1][0], "StreamChat_Refused")
            self.assertEqual(done, [])
        director, _c, done, *_ = make(state=ship_state(), act_gear=True)
        self.assertEqual(director.handle(msg("!gear")).status, "done")
        self.assertEqual(done, ["gear"])
        # lights are fine while docked
        director, _c, done, *_ = make(state=ship_state(DOCKED=True))
        self.assertEqual(director.handle(msg("!lights")).status, "done")

    def test_log_keeps_what_happened(self):
        director, *_ = make()
        director.handle(msg("hello everyone"))
        director.handle(msg("!lights"))
        self.assertEqual([r.status for r in director.log], ["done"])


class TwitchParsing(unittest.TestCase):
    LINE = ("@badge-info=subscriber/8;badges=moderator/1,subscriber/6;color=#FF0000;display-name=Gav;mod=1;subscriber=1 "
            ":gav!gav@gav.tmi.twitch.tv PRIVMSG #daddyg88 :!starling hello there")

    def test_parse_line(self):
        p = twitch.parse_line(self.LINE)
        self.assertEqual((p["command"], p["channel"], p["user"], p["text"]), ("PRIVMSG", "daddyg88", "gav", "!starling hello there"))
        self.assertEqual(twitch.parse_line("PING :tmi.twitch.tv")["command"], "PING")

    def test_message_from(self):
        m = twitch.message_from(twitch.parse_line(self.LINE), "daddyg88")
        self.assertEqual((m.user, m.mod, m.sub, m.owner), ("Gav", True, True, False))
        boss = twitch.message_from(twitch.parse_line("@badges=broadcaster/1;display-name=Dad :dad!dad@dad.tmi.twitch.tv PRIVMSG #dad :hi"), "dad")
        self.assertTrue(boss.owner and boss.mod)
        plain = twitch.message_from(twitch.parse_line("@badges=;display-name=Viewer :v!v@v.tmi.twitch.tv PRIVMSG #dad :hi"), "dad")
        self.assertEqual((plain.mod, plain.sub, plain.owner), (False, False, False))

    def test_channel_name(self):
        self.assertEqual(twitch.channel_name("Daddyg88"), "daddyg88")
        self.assertEqual(twitch.channel_name("#Daddyg88"), "daddyg88")
        self.assertEqual(twitch.channel_name("https://www.twitch.tv/Daddyg88/videos"), "daddyg88")
        self.assertEqual(twitch.channel_name("no way!"), "")
        self.assertEqual(twitch.channel_name("ab"), "")


class FakeSocket:
    def __init__(self, chunks):
        self.chunks, self.sent, self.closed = list(chunks), [], False
    def sendall(self, data): self.sent.append(data.decode())
    def recv(self, n):
        if self.chunks:
            return self.chunks.pop(0)
        return b""
    def close(self): self.closed = True


class TwitchLoop(unittest.TestCase):
    def test_a_session(self):
        sock = FakeSocket([
            b":tmi.twitch.tv 001 justinfan1 :Welcome\r\n:justinfan1!justinfan1@justinfan1.tmi.twitch.tv JOIN #daddyg88\r\nPING :tmi.twitch.tv\r\n",
            b"@badges=;display-name=Gav :gav!gav@gav.tmi.twitch.tv PRIVMSG #daddyg88 :!lig",
            b"hts\r\nRECONNECT\r\n"])
        got, statuses = [], []
        t = twitch.TwitchChat("Daddyg88", got.append, statuses.append, connect=lambda: sock, sleep=lambda s: None)
        t._session()
        self.assertTrue(any(s.startswith("PASS") for s in sock.sent))
        self.assertTrue(any(s.startswith("NICK justinfan") for s in sock.sent))
        self.assertIn("JOIN #daddyg88\r\n", sock.sent)
        self.assertIn("PONG :tmi.twitch.tv\r\n", sock.sent)
        self.assertIn("Connected to #daddyg88", statuses)
        self.assertEqual([m.text for m in got], ["!lights"])             # a message split across two reads is put back together
        self.assertTrue(sock.closed)

    def test_never_posts_anything(self):
        sock = FakeSocket([b"@badges=;display-name=G :g!g@g.tmi.twitch.tv PRIVMSG #c :!starling hi\r\n"])
        t = twitch.TwitchChat("channel", lambda m: None, lambda s: None, connect=lambda: sock, sleep=lambda s: None)
        try:
            t._session()
        except OSError:
            pass
        self.assertFalse(any(s.startswith("PRIVMSG") for s in sock.sent))

    def test_retry_then_stop(self):
        calls = []
        def boom():
            calls.append(1)
            raise OSError("no network")
        statuses = []
        t = twitch.TwitchChat("channel", lambda m: None, statuses.append, connect=boom,
                              sleep=lambda s: (calls.append(s), t._stop.set() if len(calls) > 4 else None))
        t._run()
        self.assertTrue(any("Can't reach Twitch" in s for s in statuses))
        self.assertTrue(any("Reconnecting" in s for s in statuses))


class FakeSource:
    made = []
    def __init__(self, channel, on_message, on_status):
        self.channel, self.on_message, self.on_status = channel, on_message, on_status
        self.started = self.stopped = False
        FakeSource.made.append(self)
    def start(self): self.started = True
    def stop(self): self.stopped = True


class Bridge(unittest.TestCase):
    def test_connects_and_follows_the_settings(self):
        FakeSource.made = []
        director, *_ = make()
        settings = director.settings
        bridge = ChatBridge(settings, director, source_factory=FakeSource)
        bridge.check()
        self.assertEqual(bridge.status(), "Chat is on: type your Twitch channel name")
        settings.set("streaming.twitch_channel", "https://twitch.tv/Daddyg88")
        bridge.check()
        self.assertEqual(len(FakeSource.made), 1)
        self.assertTrue(FakeSource.made[0].started)
        self.assertEqual(FakeSource.made[0].channel, "daddyg88")
        bridge.check()                                              # nothing changed: no second connection
        self.assertEqual(len(FakeSource.made), 1)
        settings.set("streaming.twitch_channel", "other_channel")
        bridge.check()
        self.assertTrue(FakeSource.made[0].stopped)
        self.assertEqual(len(FakeSource.made), 2)
        settings.set("streaming.enabled", False)
        bridge.check()
        self.assertTrue(FakeSource.made[1].stopped)
        self.assertEqual(bridge.status(), "Off")

    def test_flood_is_dropped_not_queued_forever(self):
        director, *_ = make()
        bridge = ChatBridge(director.settings, director, source_factory=FakeSource)
        for i in range(100):
            bridge.submit(msg("!lights"))
        self.assertLessEqual(bridge.queue.qsize(), 12)

    def test_pretend_and_recent(self):
        director, _c, done, *_ = make()
        bridge = ChatBridge(director.settings, director, source_factory=FakeSource)
        results = []
        import threading
        event = threading.Event()
        bridge.pretend("Tester", "!lights", done=lambda r: (results.append(r), event.set()))
        self.assertTrue(event.wait(3))
        self.assertEqual(results[0].status, "done")
        self.assertEqual(bridge.recent(), ["Tester: the ship lights -> done"])


class Voice(unittest.TestCase):
    def test_pause_and_resume(self):
        s = Settings(enabled=True)
        said = []
        class N:
            def say(self, key, fields=None): said.append(key)
        v = StreamChatVoice(s, N())
        self.assertTrue(v.try_handle("pause the chat"))
        self.assertFalse(s.get("streaming.enabled"))
        self.assertTrue(v.try_handle("turn on Twitch chat"))
        self.assertTrue(s.get("streaming.enabled"))
        self.assertTrue(v.try_handle("chat off"))
        self.assertEqual(said, ["StreamChat_Paused", "StreamChat_Resumed", "StreamChat_Paused"])

    def test_everyday_talk_is_left_alone(self):
        s = Settings(enabled=True)
        v = StreamChatVoice(s)
        for text in ("let's have a chat", "start a chat with me", "install ai chat", "tell me about the chat window", "open the galaxy map"):
            self.assertIsNone(v.try_handle(text), text)
        self.assertTrue(s.get("streaming.enabled"))


class Pieces(unittest.TestCase):
    def test_lines_and_settings_exist(self):
        with open("voicepacks/default/streaming.json", encoding="utf-8") as handle:
            data = json.load(handle)
        for key in ("StreamChat_Asks", "StreamChat_NoAnswer", "StreamChat_Action", "StreamChat_Refused", "StreamChat_Paused", "StreamChat_Resumed"):
            self.assertTrue(data[key], key)
        from core.settings import DEFAULTS
        from ui.settings_model import build_pages
        page = [p for p in build_pages() if p.id == "streaming"][0]
        for field in page.fields:
            section, _, name = field.key.partition(".")
            self.assertIn(name, DEFAULTS[section], field.key)

    def test_dialogue_loads_the_lines(self):
        from core import paths
        from personality.dialogue import DialogueManager
        d = DialogueManager(paths.VOICEPACKS_DIR / "default")
        d.load()
        self.assertIn("StreamChat_Action", d.lines)


if __name__ == "__main__":
    unittest.main()
