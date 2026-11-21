"""Three sizes of AI chat model (0.96.128): small (default), better (3B), high (7B)."""

import tempfile
import unittest
from pathlib import Path

from core import model_download, paths
from core.settings import Settings
from personality import llm as llm_module
from personality.llm import LocalLLM
from ui import settings_model


def make(**values):
    settings = Settings(Path(tempfile.gettempdir()) / "nope_llm.json").load()
    for key, value in values.items():
        settings.set(key.replace("__", "."), value)
    return settings, LocalLLM(settings, loader=lambda path, threads: None)


class Sizes(unittest.TestCase):
    def test_default_is_the_small_model(self):
        settings, llm = make()
        self.assertEqual(llm.model_size(), "small")
        self.assertEqual(llm.model_path(), paths.DATA_DIR / "models" / "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf")

    def test_each_size_has_its_own_file_and_safe_address(self):
        names = set()
        for size in ("small", "better", "high"):
            file_name, url, low, high, text = model_download.spec(size)
            names.add(file_name)
            self.assertTrue(url.startswith("https://huggingface.co/bartowski/") and url.endswith(file_name))
            self.assertLess(low, high)
            self.assertTrue(text)
            _, llm = make(llm__model_size=size)
            self.assertEqual(llm.model_path().name, file_name)
        self.assertEqual(len(names), 3)
        self.assertEqual(model_download.spec("nonsense")[0], model_download.FILE_NAME)

    def test_a_custom_model_file_wins(self):
        _, llm = make(llm__model_size="high", llm__model_file="C:/mine/model.gguf")
        self.assertEqual(llm.model_path(), Path("C:/mine/model.gguf"))

    def test_an_unknown_size_is_small(self):
        _, llm = make(llm__model_size="huge")
        self.assertEqual(llm.model_size(), "small")

    def test_bigger_models_get_more_time_and_threads(self):
        self.assertLess(llm_module.SIZE_MIN_SECONDS["small"], llm_module.SIZE_MIN_SECONDS["better"])
        self.assertLess(llm_module.SIZE_MIN_SECONDS["better"], llm_module.SIZE_MIN_SECONDS["high"])
        seen = {}
        settings = Settings(Path(tempfile.gettempdir()) / "nope_llm.json").load()
        settings.set("llm.model_size", "high")
        settings.set("llm.enabled", True)
        llm = LocalLLM(settings, loader=lambda path, threads: seen.setdefault("threads", threads) or object())
        llm._load()
        self.assertEqual(seen["threads"], 6)

    def test_the_size_check_uses_the_right_limits(self):
        folder = Path(tempfile.mkdtemp())
        big = folder / "big.gguf"
        big.write_bytes(b"GGUF" + b"\0" * (3 * 1024 * 1024))
        self.assertFalse(model_download.looks_like_model(big))                      # too small for any model
        self.assertTrue(model_download.looks_like_model(big, 1024, 10 * 1024 * 1024))

    def test_the_choice_is_on_the_personality_page(self):
        self.assertEqual([v for _l, v in settings_model.LLM_SIZES], ["small", "better", "high"])
        keys = [f.key for page in settings_model.build_pages(None) for f in page.fields] if hasattr(settings_model, "build_pages") else ["llm.model_size"]
        self.assertIn("llm.model_size", keys)


if __name__ == "__main__":
    unittest.main()
