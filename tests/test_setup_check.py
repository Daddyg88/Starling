import unittest
from types import SimpleNamespace

from ui import setup_check as sc


class FakeSettings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def fake_app(stt_enabled=True, model="base.en", folder="C:/journals", commander="Dave"):
    settings = FakeSettings({"stt.enabled": stt_enabled, "stt.model": model, "journal.folder": ""})
    ready = SimpleNamespace(is_set=lambda: True)
    kokoro = SimpleNamespace(ready=ready, failed_reason="")
    listener = SimpleNamespace(ready=ready, failed_reason="")
    return SimpleNamespace(settings=settings, journal_folder=folder, providers={"kokoro": kokoro}, listener=listener,
                           ptt=None, buttons=None, monitor=object(), mood=None,
                           state=SimpleNamespace(commander=commander, system="Sol", ship=None, ship_name=None, exobiology=None))


class SetupCheckTests(unittest.TestCase):
    def test_all_ready(self):
        items = sc.setup_items(fake_app(), key_summary=(70, 0, 0))
        self.assertTrue(sc.required_ready(items))
        self.assertIn("ready", sc.headline(items).lower())
        self.assertEqual([i["id"] for i in items], ["game", "voice", "listening", "quality", "training", "keys", "extras"])

    def test_missing_journal_folder_says_what_to_do(self):
        item = sc.game_item(fake_app(folder=None), finder=lambda _x: None)
        self.assertEqual(item["state"], sc.TODO)
        self.assertEqual(item["action"][1], "page:game")

    def test_listening_off_offers_one_button(self):
        item = sc.listening_item(fake_app(stt_enabled=False))
        self.assertEqual(item["state"], sc.TODO)
        self.assertEqual(item["action"], ("Turn listening on", "listen_on"))

    def test_smallest_model_is_a_suggestion_not_a_blocker(self):
        item = sc.quality_item(fake_app(model="tiny.en"))
        self.assertEqual(item["state"], sc.OPTIONAL)
        self.assertEqual(item["action"][1], "listen_balanced")
        self.assertEqual(sc.quality_item(fake_app(model="base.en"))["state"], sc.OK)

    def test_keys_need_the_button_first_then_report(self):
        app = fake_app()
        self.assertEqual(sc.keys_item(app)["action"][1], "check_keys")
        self.assertEqual(sc.keys_item(app, (0, 5, 0))["state"], sc.BAD)
        some = sc.keys_item(app, (60, 12, 3))
        self.assertEqual(some["state"], sc.OPTIONAL)
        self.assertIn("12 still have none", some["text"])
        self.assertIn("3 keys are shared", some["text"])

    def test_voice_loading_waits_and_problem_is_reported(self):
        app = fake_app()
        app.providers["kokoro"].ready = SimpleNamespace(is_set=lambda: False)
        self.assertEqual(sc.voice_item(app)["state"], sc.WAIT)
        app.providers["kokoro"].failed_reason = "no sound device"
        self.assertEqual(sc.voice_item(app)["state"], sc.BAD)

    def test_headline_counts_what_is_left(self):
        items = sc.setup_items(fake_app(stt_enabled=False), key_summary=None)
        self.assertFalse(sc.required_ready(items))
        self.assertIn("to do", sc.headline(items))

    def test_training_button_only_when_listening_is_on(self):
        on = [i for i in sc.setup_items(fake_app()) if i["id"] == "training"]
        self.assertEqual(on[0]["action"][1], "train_voice")
        off = sc.setup_items(fake_app(stt_enabled=False))
        self.assertNotIn("training", [i["id"] for i in off])

    def test_a_broken_app_never_raises(self):
        broken = SimpleNamespace(settings=FakeSettings())
        items = sc.setup_items(broken, finder=lambda _x: None)
        self.assertEqual(len(items), 6)


class SetupPageTests(unittest.TestCase):
    def test_get_started_is_first_in_the_sidebar_and_has_no_settings(self):
        from ui.settings_model import build_pages
        pages = build_pages()
        self.assertEqual(pages[0].id, "setup")
        self.assertEqual(pages[0].fields, [])
        self.assertEqual(pages[0].parent, "")

    def test_new_installs_listen_with_the_better_model(self):
        from core.settings import DEFAULTS
        self.assertEqual(DEFAULTS["stt"]["model"], "base.en")
        self.assertIn("first_run_done", DEFAULTS["app"])

    def test_every_action_the_page_offers_is_handled_by_the_dashboard(self):
        import re
        from pathlib import Path
        source = Path(__file__).resolve().parent.parent.joinpath("ui", "dashboard.py").read_text(encoding="utf-8")
        handled = set(re.findall(r'action == "([a-z_]+)"', source))
        offered = set()
        for items in (sc.setup_items(fake_app(stt_enabled=False, model="tiny.en")), sc.setup_items(fake_app(), (1, 1, 1))):
            for item in items:
                if item["action"] and not item["action"][1].startswith("page:"):
                    offered.add(item["action"][1])
        self.assertTrue(offered)
        self.assertLessEqual(offered, handled)


if __name__ == "__main__":
    unittest.main()
