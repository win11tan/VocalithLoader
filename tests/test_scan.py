# -*- coding: utf-8 -*-
"""路径失效后自动找回：扫描、切片、按训练目录提取。

这里全程用临时目录造场景，不碰真实的 GPT-SoVITS 安装，也不扫全盘——
真实环境里那些位置是用户的机器，测试不该依赖它们。
"""
import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import engine as engine_mod  # noqa: E402


def make_wav(path, seconds=5.0, rate=32000):
    """造一段合法的 PCM wav，内容不重要，长度对就行。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * frames)
    return path


class RoleFromNameTest(unittest.TestCase):
    def test_weight_names(self):
        self.assertEqual(core.role_from_name("helena-e12.ckpt"), "helena")
        self.assertEqual(core.role_from_name("helena_e8_s464.pth"), "helena")
        self.assertEqual(core.role_from_name("enterprise2-e8.ckpt"), "enterprise2")
        self.assertEqual(core.role_from_name("yukikaze_e4_s196.pth"), "yukikaze")

    def test_audio_names(self):
        self.assertEqual(
            core.role_from_name("cv-10205-12.wav_0000000000_0000159680.wav"),
            "cv")

    def test_empty(self):
        self.assertEqual(core.role_from_name(""), "")
        self.assertEqual(core.role_from_name(None), "")


class ScanFilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"x")
        return p

    def test_finds_by_extension(self):
        a = self.touch("models/helena-e12.ckpt")
        b = self.touch("models/helena_e8.pth")
        self.touch("models/readme.txt")
        got = core.scan_files([self.root], core.WEIGHT_EXTS, max_depth=4,
                              time_budget=5.0)
        paths = {x["path"] for x in got}
        self.assertIn(os.path.abspath(a), paths)
        self.assertIn(os.path.abspath(b), paths)
        self.assertEqual(len(got), 2)

    def test_role_is_filled(self):
        self.touch("w/helena-e12.ckpt")
        got = core.scan_files([self.root], (".ckpt",), max_depth=4,
                              time_budget=5.0)
        self.assertEqual(got[0]["role"], "helena")

    def test_name_filter(self):
        self.touch("w/helena-e12.ckpt")
        self.touch("w/yukikaze-e12.ckpt")
        got = core.scan_files([self.root], (".ckpt",),
                              name_filter=lambda low: "helena" in low,
                              max_depth=4, time_budget=5.0)
        self.assertEqual(len(got), 1)
        self.assertIn("helena", got[0]["name"])

    def test_depth_limit(self):
        # 深度 6 的文件在 max_depth=2 时不该被找到
        self.touch("a/b/c/d/e/f/deep.ckpt")
        got = core.scan_files([self.root], (".ckpt",), max_depth=2,
                              time_budget=5.0)
        self.assertEqual(got, [])

    def test_skip_dirs(self):
        self.touch("$recycle.bin/old.ckpt")
        self.touch("node_modules/dep.ckpt")
        self.touch("keep/good.ckpt")
        got = core.scan_files([self.root], (".ckpt",), max_depth=4,
                              time_budget=5.0)
        names = [x["name"] for x in got]
        self.assertEqual(names, ["good.ckpt"])

    def test_newest_first(self):
        old = self.touch("m/old.ckpt")
        new = self.touch("m/new.ckpt")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        got = core.scan_files([self.root], (".ckpt",), max_depth=4,
                              time_budget=5.0)
        self.assertEqual(got[0]["name"], "new.ckpt")

    def test_missing_root_is_ignored(self):
        self.assertEqual(
            core.scan_files([os.path.join(self.root, "nope")], (".ckpt",),
                            time_budget=1.0), [])


class SliceWavTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_slice_long_file_to_five_seconds(self):
        src = make_wav(os.path.join(self.d, "long.wav"), seconds=30.0)
        dst = os.path.join(self.d, "out.wav")
        self.assertEqual(core.slice_wav_center(src, dst, 5.0), dst)
        self.assertTrue(os.path.isfile(dst))
        self.assertAlmostEqual(core.fmt_duration(dst), 5.0, places=1)

    def test_short_file_is_kept_whole(self):
        src = make_wav(os.path.join(self.d, "short.wav"), seconds=2.0)
        dst = os.path.join(self.d, "out2.wav")
        core.slice_wav_center(src, dst, 5.0)
        self.assertAlmostEqual(core.fmt_duration(dst), 2.0, places=1)

    def test_bad_input_returns_empty(self):
        bad = os.path.join(self.d, "notaudio.wav")
        with open(bad, "wb") as f:
            f.write(b"junk")
        self.assertEqual(core.slice_wav_center(bad, os.path.join(self.d, "x.wav")), "")


class HealPathsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        self._saved = (engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR)
        engine_mod.CONFIG_PATH = os.path.join(d, "config.json")
        engine_mod.LOG_DIR = os.path.join(d, "logs")
        engine_mod.OUTPUT_DIR = os.path.join(d, "output")
        self.d = d
        self.gsv = os.path.join(d, "gsv")
        os.makedirs(os.path.join(self.gsv, "runtime"))
        os.makedirs(os.path.join(self.gsv, "GPT_weights_v2Pro"))
        os.makedirs(os.path.join(self.gsv, "SoVITS_weights_v2Pro"))
        for n in ("python.exe",):
            open(os.path.join(self.gsv, "runtime", n), "wb").close()
        open(os.path.join(self.gsv, "api_v2.py"), "wb").close()

    def tearDown(self):
        engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR = self._saved
        self._tmp.cleanup()

    def make(self):
        return engine_mod.Engine(emit=lambda k, d: None)

    def test_finds_weights_in_standard_dirs(self):
        ckpt = os.path.join(self.gsv, "GPT_weights_v2Pro", "helena-e12.ckpt")
        pth = os.path.join(self.gsv, "SoVITS_weights_v2Pro", "helena_e8_s464.pth")
        for p in (ckpt, pth):
            open(p, "wb").close()
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        e.cfg["gpt_path"] = "D:\\gone\\helena-e12.ckpt"
        e.cfg["sovits_path"] = "D:\\gone\\helena_e8_s464.pth"
        fixed = e.heal_paths(budget=0)
        names = {it["what"] for it in fixed}
        self.assertEqual(names, {"GPT 权重", "SoVITS 权重"})
        self.assertEqual(e.cfg["gpt_path"], ckpt)
        self.assertEqual(e.cfg["sovits_path"], pth)

    def test_valid_paths_are_left_alone(self):
        ckpt = os.path.join(self.gsv, "GPT_weights_v2Pro", "helena-e12.ckpt")
        open(ckpt, "wb").close()
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        e.cfg["gpt_path"] = ckpt
        e.cfg["sovits_path"] = ckpt
        fixed = e.heal_paths(budget=0)
        self.assertEqual(e.cfg["gpt_path"], ckpt)
        self.assertNotIn("GPT 权重", {it["what"] for it in fixed})

    def test_nothing_found_returns_empty(self):
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        e.cfg["gpt_path"] = "D:\\gone\\a.ckpt"
        e.cfg["sovits_path"] = "D:\\gone\\b.pth"
        e.cfg["ref_audio"] = "D:\\gone\\c.wav"
        fixed = e.heal_paths(budget=0)
        self.assertEqual(fixed, [])


class TrainingRefsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        self._saved = (engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR)
        engine_mod.CONFIG_PATH = os.path.join(d, "config.json")
        engine_mod.LOG_DIR = os.path.join(d, "logs")
        engine_mod.OUTPUT_DIR = os.path.join(d, "output")
        self.d = d
        self.gsv = os.path.join(d, "gsv")
        self.exp = os.path.join(self.gsv, "logs", "helena")
        os.makedirs(self.exp)
        self.wav_dir = os.path.join(self.exp, "5-wav32k")
        os.makedirs(self.wav_dir)

    def tearDown(self):
        engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR = self._saved
        self._tmp.cleanup()

    def make(self):
        return engine_mod.Engine(emit=lambda k, d: None)

    def test_manifest_derives_original_name(self):
        txt = os.path.join(self.exp, "2-name2text.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write("cv-10205-1.wav_0000000000_0000056640.wav\tk o\tNone\tこれだけ\n")
            f.write("cv-10205-10.wav_0000132800_0000275520.wav\ti t\tNone\t委託\n")
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        got = e._manifest_originals("helena")
        self.assertEqual(got, ["cv-10205-1.wav", "cv-10205-10.wav"])

    def test_missing_manifest_returns_empty(self):
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        self.assertEqual(e._manifest_originals("helena"), [])

    def test_uses_existing_slices(self):
        make_wav(os.path.join(self.wav_dir, "cv-1.wav_0000000000_0000160000.wav"), 5.0)
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        got = e._refs_by_training("helena", 1.0)
        self.assertTrue(got)
        self.assertTrue(os.path.isfile(got))
        self.assertAlmostEqual(e._wav_dur(got), 5.0, places=1)

    def test_role_filter_prefers_matching_exp(self):
        other = os.path.join(self.gsv, "logs", "yukikaze", "5-wav32k")
        make_wav(os.path.join(other, "y.wav"), 5.0)
        make_wav(os.path.join(self.wav_dir, "h.wav"), 5.0)
        e = self.make()
        e.cfg["gsv_dir"] = self.gsv
        got = e._refs_by_training("helena", 1.0)
        self.assertIn("helena", got)


if __name__ == "__main__":
    unittest.main()
