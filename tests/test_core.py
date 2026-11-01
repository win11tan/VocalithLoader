# -*- coding: utf-8 -*-
"""core 里那些不依赖 GPU、网络和真实权重的纯函数。

跑法：
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


class SafeFilenameTest(unittest.TestCase):
    def test_drops_reserved_chars(self):
        self.assertEqual(core.safe_filename('a/b\\c:d*e?f"g<h>i|j'), 'abcdefghij')

    def test_drops_control_chars(self):
        self.assertEqual(core.safe_filename('a\x00b\nc\td'), 'abcd')

    def test_strips_edges(self):
        self.assertEqual(core.safe_filename('  ...名字...  '), '名字')

    def test_only_punctuation_falls_back(self):
        self.assertEqual(core.safe_filename('。。。。。'), 'clip')

    def test_empty_falls_back(self):
        self.assertEqual(core.safe_filename(''), 'clip')

    def test_truncates_to_limit(self):
        self.assertEqual(len(core.safe_filename('あ' * 100)), 20)

    def test_keeps_cjk(self):
        self.assertIn('海伦娜', core.safe_filename('海伦娜说话了'))


class UniquePathTest(unittest.TestCase):
    def test_plain_when_free(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(os.path.basename(core.unique_path(d, 'a')), 'a.wav')

    def test_suffix_when_taken(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'a.wav'), 'wb').close()
            self.assertEqual(os.path.basename(core.unique_path(d, 'a')), 'a_2.wav')

    def test_walks_up(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ('a.wav', 'a_2.wav', 'a_3.wav'):
                open(os.path.join(d, n), 'wb').close()
            self.assertEqual(os.path.basename(core.unique_path(d, 'a')), 'a_4.wav')


class IsGsvDirTest(unittest.TestCase):
    def test_empty(self):
        self.assertFalse(core.is_gsv_dir(''))
        self.assertFalse(core.is_gsv_dir(None))

    def test_missing_dir(self):
        self.assertFalse(core.is_gsv_dir(os.path.join(tempfile.gettempdir(), 'no_such_dir_xyz')))

    def test_accepts_complete(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'runtime'))
            open(os.path.join(d, 'runtime', 'python.exe'), 'wb').close()
            open(os.path.join(d, 'api_v2.py'), 'w').close()
            self.assertTrue(core.is_gsv_dir(d))

    def test_rejects_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'api_v2.py'), 'w').close()  # 缺 runtime\python.exe
            self.assertFalse(core.is_gsv_dir(d))


class CheckTextTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(core.check_text(''), '文本为空')
        self.assertEqual(core.check_text('   '), '文本为空')
        self.assertEqual(core.check_text(None), '文本为空')

    def test_normal(self):
        self.assertEqual(core.check_text('今天天气不错'), '')

    def test_too_long(self):
        self.assertIn('较长', core.check_text('あ' * 3001))

    def test_punctuation_only(self):
        self.assertIn('没有可发音', core.check_text('。。。！？'))


class FmtDurationTest(unittest.TestCase):
    def test_missing_file(self):
        p = os.path.join(tempfile.gettempdir(), 'definitely_not_here.wav')
        self.assertEqual(core.fmt_duration(p), 0.0)

    def test_real_wav(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.wav')
            with wave.open(p, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b'\x00\x00' * 8000)  # 16000Hz 下正好 0.5 秒
            self.assertAlmostEqual(core.fmt_duration(p), 0.5, places=2)


if __name__ == '__main__':
    unittest.main()
