import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _s(text):
    raw = text.encode()
    return struct.pack("<Q", len(raw)) + raw


def make_gguf(path, layers=28):
    kv = (_s("general.architecture") + struct.pack("<I", 8) + _s("llama")
          + _s("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2) + _s("a") + _s("bb")        # an array of strings to skip over
          + _s("general.file_type") + struct.pack("<II", 4, 7)
          + _s("llama.block_count") + struct.pack("<II", 4, layers))
    Path(path).write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 5) + kv)


class GpuLimitTests(unittest.TestCase):
    def setUp(self):
        from core import gpu_limit
        self.gl = gpu_limit
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self.gl.set_percent, 100)

    def test_layer_count_is_read_from_the_model_file(self):
        make_gguf(self.tmp / "m.gguf", 28)
        self.assertEqual(self.gl.model_layers(self.tmp / "m.gguf"), 28)
        self.assertEqual(self.gl.model_layers(self.tmp / "missing.gguf"), 0)
        (self.tmp / "junk.gguf").write_bytes(b"not a model")
        self.assertEqual(self.gl.model_layers(self.tmp / "junk.gguf"), 0)

    def test_seventy_percent_of_the_layers_go_on_the_card(self):
        make_gguf(self.tmp / "m.gguf", 28)
        self.assertEqual(self.gl.gpu_layers(self.tmp / "m.gguf", 70), 20)        # 28 * 0.7 = 19.6
        self.assertEqual(self.gl.gpu_layers(self.tmp / "m.gguf", 100), 99)       # no limit = everything, as before
        self.assertEqual(self.gl.gpu_layers(self.tmp / "unreadable.gguf", 70), 22)   # unknown size: 32 layers assumed
        self.assertGreaterEqual(self.gl.gpu_layers(self.tmp / "m.gguf", 10), 1)

    def test_the_engine_command_uses_the_limit(self):
        from personality import llm_server
        make_gguf(self.tmp / "m.gguf", 28)
        self.gl.set_percent(70)
        self.assertEqual(llm_server.ServerModel("x.exe", self.tmp / "m.gguf", gpu=True).command()[-2:], ["-ngl", "20"])
        self.gl.set_percent(100)
        self.assertEqual(llm_server.ServerModel("x.exe", self.tmp / "m.gguf", gpu=True).command()[-2:], ["-ngl", "99"])
        self.assertNotIn("-ngl", llm_server.ServerModel("x.exe", self.tmp / "m.gguf").command())      # the processor engine is not touched

    def test_the_voice_memory_is_capped(self):
        torch = mock.Mock()
        torch.cuda.is_available.return_value = True
        self.assertIn("70%", self.gl.cap_torch_memory(torch, 70))
        torch.cuda.set_per_process_memory_fraction.assert_called_once_with(0.7, 0)
        torch2 = mock.Mock()
        self.assertEqual(self.gl.cap_torch_memory(torch2, 100), "")
        torch2.cuda.set_per_process_memory_fraction.assert_not_called()
        torch3 = mock.Mock()
        torch3.cuda.is_available.return_value = False                              # no graphics card: nothing to cap
        self.assertEqual(self.gl.cap_torch_memory(torch3, 70), "")
        torch4 = mock.Mock()
        torch4.cuda.is_available.return_value = True
        torch4.cuda.set_per_process_memory_fraction.side_effect = RuntimeError("boom")
        self.assertIn("Could not cap", self.gl.cap_torch_memory(torch4, 70))       # never stops her voice

    def test_the_setting_exists_and_defaults_to_seventy(self):
        from core.settings import DEFAULTS
        from ui import settings_model
        self.assertEqual(DEFAULTS["gpu"]["limit_percent"], 70)
        keys = [f.key for page in settings_model.build_pages() for f in page.fields]
        self.assertIn("gpu.limit_percent", keys)
        self.gl.set_percent("garbage")
        self.assertEqual(self.gl.percent(), 100)
        self.gl.set_percent(5)
        self.assertEqual(self.gl.percent(), 10)


if __name__ == "__main__":
    unittest.main()
