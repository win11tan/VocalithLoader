# -*- coding: utf-8 -*-
"""Engine 里不依赖推理服务的部分：配置读写、目录检查、自检结构。

CONFIG_PATH / LOG_DIR / OUTPUT_DIR 都是模块级常量，这里在 setUp 里换成临时
目录，避免测试动到仓库里真实的 config.json。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import engine as engine_mod  # noqa: E402


class EngineTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        self._saved = (engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR)
        engine_mod.CONFIG_PATH = os.path.join(d, "config.json")
        engine_mod.LOG_DIR = os.path.join(d, "logs")
        engine_mod.OUTPUT_DIR = os.path.join(d, "output")
        self.logs = []

    def tearDown(self):
        engine_mod.CONFIG_PATH, engine_mod.LOG_DIR, engine_mod.OUTPUT_DIR = self._saved
        self._tmp.cleanup()

    def make(self):
        return engine_mod.Engine(emit=lambda k, d: self.logs.append(d.get("line", ""))
                                 if k == "log" else None)


class CreateDirsTest(EngineTestBase):
    def test_engine_creates_output_and_log_dirs(self):
        # 这正是 1.0.0 里漏掉的那一步：目录不存在，却要等到合成最后一步才报错
        self.assertFalse(os.path.isdir(engine_mod.OUTPUT_DIR))
        self.make()
        self.assertTrue(os.path.isdir(engine_mod.OUTPUT_DIR))
        self.assertTrue(os.path.isdir(engine_mod.LOG_DIR))


class LoadConfigTest(EngineTestBase):
    def test_defaults_when_missing(self):
        e = self.make()
        self.assertEqual(e.cfg["port"], core.DEFAULT_CONFIG["port"])
        self.assertTrue(e.cfg["batch_lines"])

    def test_reads_existing_values(self):
        with open(engine_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"port": 1234, "text_lang": "zh"}, f)
        e = self.make()
        self.assertEqual(e.cfg["port"], 1234)
        self.assertEqual(e.cfg["text_lang"], "zh")

    def test_corrupt_file_falls_back_and_says_so(self):
        with open(engine_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        e = self.make()
        self.assertEqual(e.cfg["port"], core.DEFAULT_CONFIG["port"])
        self.assertTrue(any("配置文件读不出来" in line for line in self.logs))

    def test_save_then_reload(self):
        e = self.make()
        e.cfg["port"] = 9999
        e.save_config()
        e2 = self.make()
        self.assertEqual(e2.cfg["port"], 9999)


class ImportExportTest(EngineTestBase):
    def test_export_returns_json(self):
        e = self.make()
        r = e.export_config()
        self.assertTrue(r["ok"])
        self.assertEqual(json.loads(r["data"])["port"], e.cfg["port"])

    def test_import_rejects_bad_json(self):
        e = self.make()
        r = e.import_config("not json at all")
        self.assertFalse(r["ok"])
        self.assertIn("JSON", r["msg"])

    def test_import_rejects_non_object(self):
        e = self.make()
        r = e.import_config("[1, 2, 3]")
        self.assertFalse(r["ok"])

    def test_import_accepts_known_keys_only(self):
        e = self.make()
        r = e.import_config(json.dumps({"port": 7777, "definitely_not_a_field": 1}))
        self.assertTrue(r["ok"])
        self.assertEqual(e.cfg["port"], 7777)
        self.assertNotIn("definitely_not_a_field", e.cfg)


class DirWritableTest(EngineTestBase):
    def test_writable_dir(self):
        e = self.make()
        self.assertTrue(e._dir_writable(os.path.join(self._tmp.name, "somewhere")))

    def test_unwritable_or_broken_path(self):
        e = self.make()
        self.assertFalse(e._dir_writable(r"Z:\definitely\not\available"))

    def test_does_not_leave_probe_file(self):
        e = self.make()
        target = os.path.join(self._tmp.name, "probe")
        self.assertTrue(e._dir_writable(target))
        self.assertEqual(os.listdir(target), [])


class SelfCheckTest(EngineTestBase):
    def test_returns_four_tuple_per_item(self):
        e = self.make()
        items = e.self_check()
        self.assertTrue(items)
        for it in items:
            self.assertEqual(len(it), 4, "每项应当是 [名称, 是否正常, 说明, 是否必需]")
            name, ok, detail, required = it
            self.assertIsInstance(name, str)
            self.assertIsInstance(ok, bool)
            self.assertIsInstance(required, bool)

    def test_output_and_log_dirs_are_required_items(self):
        e = self.make()
        names = [it[0] for it in e.self_check()]
        self.assertIn("输出目录", names)
        self.assertIn("日志目录", names)

    def test_ffmpeg_is_optional(self):
        e = self.make()
        rows = {it[0]: it for it in e.self_check()}
        self.assertFalse(rows["ffmpeg"][3], "ffmpeg 只影响导 mp3，不该算必需")

    def test_missing_requests_is_blocking(self):
        e = self.make()
        saved = engine_mod.requests
        try:
            engine_mod.requests = None
            items = e.self_check()
            rows = {it[0]: it for it in items}
            self.assertFalse(rows["requests 模块"][1])
            self.assertTrue(rows["requests 模块"][3])
        finally:
            engine_mod.requests = saved

    def test_version_is_listed_first(self):
        # 用户报问题的时候经常说不清自己在用哪一版。自检清单是唯一一个
        # 他会主动截图的地方，所以版本必须出现在这里，而且排第一行。
        e = self.make()
        items = e.self_check()
        self.assertEqual(items[0][0], "VocalithLoader")
        self.assertEqual(items[0][2], core.APP_VERSION)
        self.assertTrue(items[0][1], "版本行只是拿来显示的，不该显示成失败")
        self.assertFalse(items[0][3], "版本不该算必需项，不该拦着人用")


if __name__ == "__main__":
    unittest.main()
