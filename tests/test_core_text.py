# -*- coding: utf-8 -*-
"""颜色、名称压缩、设备配置读写。都是不碰推理的纯逻辑。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


class ColorTest(unittest.TestCase):
    def test_mix_ends(self):
        self.assertEqual(core.mix("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(core.mix("#000000", "#ffffff", 1.0), "#ffffff")

    def test_mix_midpoint(self):
        # 0 + (255-0) * 0.5 = 127.5 -> int() 截成 127 = 0x7f
        self.assertEqual(core.mix("#000000", "#ffffff", 0.5), "#7f7f7f")

    def test_mix_clamps_out_of_range(self):
        self.assertEqual(core.mix("#000000", "#ffffff", -1), "#000000")
        self.assertEqual(core.mix("#000000", "#ffffff", 2), "#ffffff")

    def test_glow_zero_is_identity(self):
        self.assertEqual(core.glow("#123456", 0), "#123456")

    def test_glow_lightens(self):
        self.assertNotEqual(core.glow("#000000", 0.35), "#000000")


class ShortNameTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(core.short_name(""), "")
        self.assertEqual(core.short_name(None), "")

    def test_strips_trademark_and_vendor(self):
        self.assertEqual(core.short_name("Intel(R) Core(TM) Ultra 9 275HX"),
                         "Core Ultra 9 275HX")

    def test_strips_cpu_frequency_tail(self):
        self.assertEqual(core.short_name("Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"),
                         "Core i7-9750H")

    def test_strips_gpu_suffix(self):
        self.assertEqual(core.short_name("NVIDIA GeForce RTX 5060 Laptop GPU"),
                         "GeForce RTX 5060 Laptop")

    def test_strips_processor_suffix(self):
        self.assertEqual(core.short_name("AMD Ryzen 7 5800X 8-Core Processor"),
                         "Ryzen 7 5800X 8-Core")


class LooksLikeGsvNameTest(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(core.looks_like_gsv_name("SoVITS"))
        self.assertTrue(core.looks_like_gsv_name("GPT-SoVITS-v2pro-20250604"))
        self.assertTrue(core.looks_like_gsv_name("gpt-sovits"))

    def test_rejects_unrelated(self):
        self.assertFalse(core.looks_like_gsv_name("downloads"))
        self.assertFalse(core.looks_like_gsv_name(""))
        self.assertFalse(core.looks_like_gsv_name("Documents"))


class YamlPathTest(unittest.TestCase):
    def test_ends_with_expected_relative_path(self):
        p = core.yaml_path_of(r"D:\some\gsv")
        self.assertTrue(p.endswith(os.path.join("GPT_SoVITS", "configs", "tts_infer.yaml")))


class DeviceConfigTest(unittest.TestCase):
    YAML = (
        "custom:\n"
        "  device: cuda\n"
        "  is_half: true\n"
        "\n"
        "v1:\n"
        "  device: cuda\n"
    )

    def _make(self, d):
        cfg_dir = os.path.join(d, "GPT_SoVITS", "configs")
        os.makedirs(cfg_dir)
        p = os.path.join(cfg_dir, "tts_infer.yaml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.YAML)
        return p

    def test_defaults_to_cuda_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(core.read_device(d), "cuda")

    def test_reads_existing(self):
        with tempfile.TemporaryDirectory() as d:
            self._make(d)
            self.assertEqual(core.read_device(d), "cuda")

    def test_write_then_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make(d)
            ok, msg = core.write_device(d, "cpu")
            self.assertTrue(ok, msg)
            self.assertEqual(core.read_device(d), "cpu")
            with open(p, encoding="utf-8") as f:
                text = f.read()
            # CPU 下必须把 is_half 关掉，否则半精度会直接报错
            self.assertIn("is_half: false", text)

    def test_write_leaves_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make(d)
            core.write_device(d, "cpu")
            self.assertTrue(os.path.isfile(p + ".bak"))

    def test_missing_yaml_reports_clearly(self):
        with tempfile.TemporaryDirectory() as d:
            ok, msg = core.write_device(d, "cpu")
            self.assertFalse(ok)
            self.assertIn("找不到", msg)


if __name__ == "__main__":
    unittest.main()
