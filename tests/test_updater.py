import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import updater
from core.updater import UpdateError


def make_zip(files, top=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, text in files.items():
            z.writestr((top + "/" + name) if top else name, text)
    return buffer.getvalue()


class Reply(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeNet:
    def __init__(self, zip_bytes, sha=None, release=None):
        self.zip = zip_bytes
        self.sha = sha or hashlib.sha256(zip_bytes).hexdigest()
        self.release = release

    def __call__(self, request, timeout=0):
        url = request.full_url
        if url.endswith("/releases/latest"):
            if self.release is None:
                raise OSError("offline")
            return Reply(json.dumps(self.release).encode())
        if url.endswith(updater.ASSET_SHA):
            return Reply((self.sha + "  Starling-app.zip\n").encode())
        if url.endswith(updater.ASSET_ZIP):
            return Reply(self.zip)
        raise OSError(url)


def release(tag="v0.12.0"):
    base = "https://example/dl/"
    return {"tag_name": tag, "body": "notes", "assets": [
        {"name": updater.ASSET_ZIP, "browser_download_url": base + updater.ASSET_ZIP},
        {"name": updater.ASSET_SHA, "browser_download_url": base + updater.ASSET_SHA}]}


GOOD = {"main.py": "print('new')", "core/__init__.py": "", "config/settings.json": "{}", "NEW.txt": "new"}


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updater.parse_version("v0.11.0"), (0, 11, 0))
        self.assertTrue(updater.is_newer("0.12.0", "0.11.0"))
        self.assertTrue(updater.is_newer("v0.11.1", "0.11.0 (Phase 6)"))
        self.assertFalse(updater.is_newer("0.11.0", "0.11.0"))
        self.assertFalse(updater.is_newer("0.9.9", "0.11.0"))
        self.assertTrue(updater.is_newer("0.11.0.1", "0.11.0"))
        self.assertFalse(updater.is_newer("garbage", "0.11.0"))


class FetchTests(unittest.TestCase):
    def test_finds_the_release(self):
        info = updater.fetch_latest("Ben/Starling", opener=FakeNet(b"", release=release()))
        self.assertEqual(info["version"], "0.12.0")

    def test_bad_repo_names_are_refused_before_any_network(self):
        for repo in ("", "nonsense", "a/b/c", "../x/y"):
            with self.assertRaises(UpdateError):
                updater.fetch_latest(repo, opener=lambda *a, **k: self.fail("went online"))

    def test_offline_gives_a_plain_message(self):
        with self.assertRaises(UpdateError) as caught:
            updater.fetch_latest("Ben/Starling", opener=FakeNet(b"", release=None))
        self.assertIn("Could not reach GitHub", str(caught.exception))

    def test_release_without_assets_is_refused(self):
        bad = release()
        bad["assets"] = []
        with self.assertRaises(UpdateError):
            updater.fetch_latest("Ben/Starling", opener=FakeNet(b"", release=bad))


class StageAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = self.root / "app"
        (self.app / "data").mkdir(parents=True)
        (self.app / "config").mkdir()
        (self.app / "core").mkdir()
        (self.app / "main.py").write_text("print('old')")
        (self.app / "data" / "mood.json").write_text('{"score": 42}')
        (self.app / "config" / "settings.json").write_text('{"mine": true}')
        (self.app / "OLD.txt").write_text("old")
        self.updates = self.root / "updates"
        self.info = {"version": "0.12.0", "zip_url": "https://example/dl/" + updater.ASSET_ZIP,
                     "sha_url": "https://example/dl/" + updater.ASSET_SHA}

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, files=GOOD, **kw):
        return updater.stage_update(self.info, self.updates, opener=FakeNet(make_zip(files, **kw)))

    def test_download_stages_without_touching_the_live_folder(self):
        self.stage()
        self.assertTrue((self.updates / "pending" / "NEW.txt").exists())
        self.assertEqual((self.app / "main.py").read_text(), "print('old')")
        self.assertEqual(updater.pending_version(self.updates), "0.12.0")

    def test_a_zip_with_one_top_folder_still_works(self):
        self.stage(top="Starling")
        self.assertTrue((self.updates / "pending" / "main.py").exists())

    def test_wrong_fingerprint_is_thrown_away(self):
        net = FakeNet(make_zip(GOOD), sha="0" * 64)
        with self.assertRaises(UpdateError) as caught:
            updater.stage_update(self.info, self.updates, opener=net)
        self.assertIn("fingerprint", str(caught.exception))
        self.assertFalse((self.updates / "pending").exists())
        self.assertIsNone(updater.pending_version(self.updates))

    def test_unsafe_paths_are_refused(self):
        with self.assertRaises(UpdateError):
            self.stage({"../evil.txt": "x", "main.py": "", "core/a": ""})
        self.assertFalse((self.root / "evil.txt").exists())

    def test_something_that_is_not_starling_is_refused(self):
        with self.assertRaises(UpdateError):
            self.stage({"readme.txt": "hi"})

    def test_apply_swaps_and_keeps_your_files(self):
        self.stage()
        self.assertEqual(updater.apply_pending(self.app, self.updates), "0.12.0")
        self.assertEqual((self.app / "main.py").read_text(), "print('new')")
        self.assertEqual((self.app / "data" / "mood.json").read_text(), '{"score": 42}')
        self.assertEqual((self.app / "config" / "settings.json").read_text(), '{"mine": true}')
        self.assertTrue((self.app / "NEW.txt").exists())
        self.assertFalse((self.app / "OLD.txt").exists())
        self.assertTrue((self.root / "app.previous" / "OLD.txt").exists())
        self.assertIsNone(updater.pending_version(self.updates))

    def test_nothing_pending_does_nothing(self):
        self.assertIsNone(updater.apply_pending(self.app, self.updates))

    def test_failed_startup_test_rolls_back(self):
        self.stage()
        with self.assertRaises(UpdateError):
            updater.apply_pending(self.app, self.updates, check=lambda folder: False)
        self.assertEqual((self.app / "main.py").read_text(), "print('old')")
        self.assertTrue((self.app / "OLD.txt").exists())
        self.assertIsNone(updater.pending_version(self.updates))

    def test_a_crashing_startup_test_also_rolls_back(self):
        self.stage()

        def boom(folder):
            raise RuntimeError("x")
        with self.assertRaises(UpdateError):
            updater.apply_pending(self.app, self.updates, check=boom)
        self.assertEqual((self.app / "main.py").read_text(), "print('old')")

    def test_manual_roll_back(self):
        self.stage()
        updater.apply_pending(self.app, self.updates)
        self.assertTrue(updater.roll_back(self.app))
        self.assertEqual((self.app / "main.py").read_text(), "print('old')")
        self.assertFalse(updater.roll_back(self.root / "nowhere"))


if __name__ == "__main__":
    unittest.main()
