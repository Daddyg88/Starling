import json
import unittest

from control.matcher import Matcher
from journal.game_state import GameState
from streaming import chat, twitch, youtube
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
        self.assertTrue(bridge.status().startswith("Chat is on"))
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


def yt_page(items=(), token="t1", wait=5000):
    return {"nextPageToken": token, "pollingIntervalMillis": wait, "items": list(items)}


def yt_item(text, name="Gav", kind="textMessageEvent", **author):
    return {"snippet": {"type": kind, "textMessageDetails": {"messageText": text}}, "authorDetails": dict({"displayName": name}, **author)}


class YouTubeParsing(unittest.TestCase):
    def test_video_id(self):
        vid = "dQw4w9WgXcQ"
        for text in (vid, "https://www.youtube.com/watch?v=" + vid, "https://youtu.be/" + vid + "?t=4",
                     "https://www.youtube.com/live/" + vid + "?feature=share", "  " + vid + " "):
            self.assertEqual(youtube.video_id(text), vid, text)
        for text in ("", "hello", "https://example.com", None):
            self.assertEqual(youtube.video_id(text), "")

    def test_poll_seconds_never_burns_quota(self):
        self.assertEqual(youtube.poll_seconds(1000), 10.0)
        self.assertEqual(youtube.poll_seconds(25000), 25.0)
        self.assertEqual(youtube.poll_seconds(900000), 60.0)
        self.assertEqual(youtube.poll_seconds("x"), 10.0)

    def test_messages_and_badges(self):
        page = yt_page([yt_item("!lights"), yt_item("hi", "Mod", isChatModerator=True), yt_item("boss", "Me", isChatOwner=True),
                        yt_item("member", "Sub", isChatSponsor=True), yt_item("5 dollars", "Rich", kind="superChatEvent")])
        found = youtube.parse_messages(page)
        self.assertEqual([m.user for m in found], ["Gav", "Mod", "Me", "Sub"])
        self.assertTrue(found[1].mod and not found[1].owner)
        self.assertTrue(found[2].owner and found[2].mod)
        self.assertTrue(found[3].sub)
        self.assertEqual(found[0].platform, "youtube")
        self.assertEqual(youtube.parse_messages({}), [])

    def test_error_reason_and_key_shape(self):
        self.assertEqual(youtube.error_reason('{"error":{"errors":[{"reason":"quotaExceeded"}]}}'), "quotaExceeded")
        self.assertEqual(youtube.error_reason("not json"), "")
        self.assertTrue(youtube.looks_like_key("AIzaSyA" + "b" * 32))
        self.assertFalse(youtube.looks_like_key("short"))


class YouTubeLoop(unittest.TestCase):
    def make(self, answers):
        got, status, calls = [], [], []
        queue_ = list(answers)

        def fake_get(url):
            calls.append(url)
            answer = queue_.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        chat_ = youtube.YouTubeChat("KEY123", "dQw4w9WgXcQ", got.append, status.append, get=fake_get, sleep=lambda s: None)
        return chat_, got, status, calls

    def test_finds_chat_skips_backlog_then_delivers_new_messages(self):
        live = {"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT1"}}]}
        chat_, got, status, calls = self.make([live, yt_page([yt_item("old one")], "t1"), yt_page([yt_item("!lights")], "t2")])
        self.assertEqual(chat_.step(), 0.0)
        self.assertEqual(chat_.step(), 10.0)
        self.assertEqual(got, [])                                  # the backlog is never acted on
        chat_.step()
        self.assertEqual([m.text for m in got], ["!lights"])
        self.assertIn("pageToken=t1", calls[2])
        self.assertIn("liveChatId=CHAT1", calls[1])
        self.assertEqual(status[-1], "Connected to the YouTube live chat")

    def test_waits_when_not_live(self):
        chat_, got, status, _ = self.make([{"items": [{"liveStreamingDetails": {}}]}, {"items": []}])
        self.assertEqual(chat_.step(), youtube.NO_CHAT_RETRY)
        self.assertIn("no live chat", status[-1])
        self.assertEqual(chat_.step(), youtube.NO_CHAT_RETRY)
        self.assertIn("can't find that video", status[-1])

    def test_problems_never_crash_and_never_show_the_key(self):
        statuses = []
        chat_, _g, status, _c = self.make([])
        chat_.on_status = statuses.append
        self.assertEqual(chat_._api_problem(youtube.ApiError(403, "quotaExceeded")), youtube.QUOTA_RETRY)
        self.assertIn("daily limit", statuses[-1])
        self.assertEqual(chat_._api_problem(youtube.ApiError(400, "keyInvalid")), youtube.KEY_RETRY)
        self.assertIn("refused the key", statuses[-1])
        chat_.chat_id = "X"
        chat_._api_problem(youtube.ApiError(403, "liveChatEnded"))
        self.assertEqual(chat_.chat_id, "")
        chat_._api_problem(youtube.ApiError(500, ""))
        self.assertTrue(all("KEY123" not in s for s in statuses))

    def test_run_survives_network_errors(self):
        chat_, _g, status, _c = self.make([OSError("down"), RuntimeError("boom")])
        waits = []
        def sleep(s):
            waits.append(s)
            if len(waits) >= 2:
                chat_._stop.set()
        chat_._sleep = sleep
        chat_._run()
        self.assertEqual(waits[:2], [15.0, 30.0])
        self.assertTrue(any("Can't reach YouTube" in s for s in status))

    def test_needs_key_and_video(self):
        self.assertIsNone(youtube.YouTubeChat("", "dQw4w9WgXcQ", None, None).start())
        a = youtube.YouTubeChat("k" * 30, "nonsense", None, None)
        a.start()
        self.assertIsNone(a._thread)


class BridgeBothPlatforms(unittest.TestCase):
    def test_youtube_needs_key_and_link_and_both_can_run(self):
        FakeSource.made = []
        yt = []

        class FakeYT:
            def __init__(self, key, video, on_message, on_status):
                self.key, self.video, self.on_status, self.stopped = key, video, on_status, False
                yt.append(self)
            def start(self): pass
            def stop(self): self.stopped = True

        director, *_ = make()
        s = director.settings
        bridge = ChatBridge(s, director, source_factory=FakeSource, youtube_factory=FakeYT)
        s.set("streaming.youtube_video", "https://youtu.be/dQw4w9WgXcQ")
        bridge.check()
        self.assertEqual(yt, [])                                    # a link alone is not enough
        s.set("streaming.youtube_key", "K" * 35)
        bridge.check()
        self.assertEqual(len(yt), 1)
        self.assertEqual(yt[0].video, "dQw4w9WgXcQ")
        yt[0].on_status("Connected to the YouTube live chat")
        self.assertEqual(bridge.status(), "Connected to the YouTube live chat")
        s.set("streaming.twitch_channel", "daddyg88")
        bridge.check()
        self.assertEqual(len(yt), 1)                                # YouTube was not restarted
        self.assertIn("YouTube: Connected", bridge.status())
        self.assertIn("Twitch:", bridge.status())
        s.set("streaming.youtube_video", "")
        bridge.check()
        self.assertTrue(yt[0].stopped)
        s.set("streaming.enabled", False)
        bridge.check()
        self.assertEqual(bridge.status(), "Off")


class HeldQuestions(unittest.TestCase):
    def build(self, **settings):
        director, clock, done, asked, _said = make(**settings)
        self.quiet = [False]
        director.quiet_provider = lambda: self.quiet[0]
        return director, clock, asked

    def test_question_waits_while_busy_then_is_answered(self):
        director, clock, asked = self.build()
        result = director.handle(msg("!starling what is a neutron star?"))
        self.assertEqual(result.status, "held")
        self.assertEqual(asked, [])
        self.assertIsNone(director.pump())                    # still busy
        self.quiet[0] = True
        answered = director.pump()
        self.assertEqual(answered.status, "answered")
        self.assertEqual(asked, [("Gav", "what is a neutron star?")])

    def test_quiet_means_answered_at_once(self):
        director, clock, asked = self.build()
        self.quiet[0] = True
        self.assertEqual(director.handle(msg("!starling hello there")).status, "answered")

    def test_cap_of_four_and_oldest_first(self):
        director, clock, asked = self.build()
        for i in range(4):
            self.assertEqual(director.handle(msg("!starling question %d" % i, user="User%d" % i)).status, "held")
        over = director.handle(msg("!starling one too many", user="Late"))
        self.assertEqual(over.status, "blocked")
        self.assertIn("too many", over.note)
        self.quiet[0] = True
        director.pump()
        clock.now += 11
        director.pump()
        self.assertEqual([q for _u, q in asked], ["question 0", "question 1"])

    def test_cap_is_a_setting(self):
        director, clock, asked = self.build(hold_max=2)
        director.handle(msg("!starling one", user="A"))
        director.handle(msg("!starling two", user="B"))
        self.assertEqual(director.handle(msg("!starling three", user="C")).status, "blocked")

    def test_old_questions_are_dropped(self):
        director, clock, asked = self.build()
        director.handle(msg("!starling old one"))
        clock.now += 400
        self.quiet[0] = True
        self.assertIsNone(director.pump())
        self.assertEqual(asked, [])

    def test_actions_are_never_held(self):
        director, clock, asked = self.build()
        self.assertEqual(director.handle(msg("!lights")).status, "done")

    def test_same_viewer_cannot_queue_twice(self):
        director, clock, asked = self.build()
        director.handle(msg("!starling one"))
        self.assertEqual(director.handle(msg("!starling two")).status, "cooldown")

    def test_switching_hold_off_answers_at_once(self):
        director, clock, asked = self.build(hold=False)
        self.assertEqual(director.handle(msg("!starling hi")).status, "answered")
