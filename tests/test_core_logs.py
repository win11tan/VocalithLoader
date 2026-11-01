# -*- coding: utf-8 -*-
"""日志解析：进度标记、加载项、tqdm 百分比。

这些全是对文本的处理，不需要真的跑起推理服务。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


def write(path, data, mode="ab"):
    with open(path, mode) as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


class CountMarksTest(unittest.TestCase):
    def test_missing_file(self):
        off, n = core.count_marks(os.path.join(tempfile.gettempdir(), "no_such.log"), 0, "x")
        self.assertEqual(n, 0)

    def test_nothing_new(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, "abc")
            off, n = core.count_marks(p, 3, "abc")
            self.assertEqual(n, 0)
            self.assertEqual(off, 3)

    def test_counts_all_occurrences(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, "hit hit hit hit hit")
            off, n = core.count_marks(p, 0, "hit")
            self.assertEqual(n, 5)
            self.assertLessEqual(off, os.path.getsize(p))

    def test_incremental_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, "hit hit ")
            off, n1 = core.count_marks(p, 0, "hit")
            self.assertEqual(n1, 2)
            write(p, "hit")
            off2, n2 = core.count_marks(p, off, "hit")
            self.assertEqual(n2, 1)  # 只该数到新追加的那条

    def test_utf8_mark(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, core.PROGRESS_MARK + "\n")
            off, n = core.count_marks(p, 0, core.PROGRESS_MARK)
            self.assertEqual(n, 1)

    def test_read_progress_uses_progress_mark(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, (core.PROGRESS_MARK + "\n") * 3)
            off, n = core.read_progress(p, 0)
            self.assertEqual(n, 3)


class ScanLoadTest(unittest.TestCase):
    SAMPLE = (
        "Loading Text2Semantic weights\n"
        "Loading VITS weights\n"
        "t2s_weights_path: a.ckpt\n"
        "vits_weights_path: b.pth\n"
        "bert_base_path: /x\n"
    )

    def test_missing_file(self):
        self.assertEqual(
            core.scan_load(os.path.join(tempfile.gettempdir(), "no_such.log"), 0),
            (0, 0, 0, None),
        )

    def test_counts_steps_config_and_last_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, self.SAMPLE)
            off, steps, conf, name = core.scan_load(p, 0)
            self.assertEqual(steps, 2)          # 两行 Loading
            self.assertEqual(conf, 3)           # 配置里三个权重键
            self.assertEqual(name, "VITS")      # 最近加载的那项

    def test_read_load_steps(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.log")
            write(p, self.SAMPLE)
            off, n = core.read_load_steps(p, 0)
            self.assertEqual(n, 2)


class ReadTqdmTest(unittest.TestCase):
    def test_parses_percent(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.log")
            write(p, "  42%|####      | 630/1500 [00:01<00:02, 1.2it/s]")
            off, frac = core.read_tqdm(p, 0)
            self.assertAlmostEqual(frac, 0.42, places=2)

    def test_returns_none_without_tqdm(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.log")
            write(p, "just some ordinary output\n")
            off, frac = core.read_tqdm(p, 0)
            self.assertIsNone(frac)

    def test_missing_file(self):
        off, frac = core.read_tqdm(os.path.join(tempfile.gettempdir(), "no_such.log"), 0)
        self.assertIsNone(frac)


class CountSentencesTest(unittest.TestCase):
    def test_empty_still_one(self):
        self.assertEqual(core.count_sentences(""), 1)
        self.assertEqual(core.count_sentences(None), 1)
        self.assertEqual(core.count_sentences("   "), 1)

    def test_single(self):
        self.assertEqual(core.count_sentences("你好"), 1)

    def test_multiple_by_punctuation(self):
        self.assertEqual(core.count_sentences("一。二。三。"), 3)

    def test_multiple_by_newline(self):
        self.assertEqual(core.count_sentences("a\nb\r\nc"), 3)

    def test_punctuation_only_never_zero(self):
        self.assertGreaterEqual(core.count_sentences("。。。"), 1)


if __name__ == "__main__":
    unittest.main()
