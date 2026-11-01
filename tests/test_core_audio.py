# -*- coding: utf-8 -*-
"""波形与频谱。用临时生成的 wav 测，不碰真实音频。"""
import array
import math
import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402

try:
    import numpy  # noqa: F401
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False


def make_wav(path, frames=8000, rate=16000, channels=1, amp=0, freq=440.0):
    """写一段 wav。amp=0 是静音，否则是正弦波。"""
    samples = []
    for i in range(frames):
        v = int(amp * math.sin(2.0 * math.pi * freq * i / rate)) if amp else 0
        for _ in range(channels):
            samples.append(v)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array.array("h", samples).tobytes())


class ReadPeaksTest(unittest.TestCase):
    def test_missing_file(self):
        self.assertEqual(core.read_peaks(os.path.join(tempfile.gettempdir(), "no.wav")), [])

    def test_silence_returns_flat_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.wav")
            make_wav(p, amp=0)
            peaks = core.read_peaks(p, buckets=32)
            self.assertEqual(len(peaks), 32)
            self.assertTrue(all(v == 0.0 for v in peaks))

    def test_signal_is_normalised_to_one(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.wav")
            make_wav(p, amp=16000)
            peaks = core.read_peaks(p, buckets=32)
            self.assertEqual(len(peaks), 32)
            self.assertAlmostEqual(max(peaks), 1.0, places=6)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in peaks))

    def test_default_bucket_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.wav")
            make_wav(p, amp=8000)
            self.assertEqual(len(core.read_peaks(p)), 96)

    def test_stereo_is_handled(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "st.wav")
            make_wav(p, channels=2, amp=12000)
            peaks = core.read_peaks(p, buckets=16)
            self.assertEqual(len(peaks), 16)

    def test_empty_wav(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.wav")
            with wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"")
            self.assertEqual(core.read_peaks(p), [])


@unittest.skipUnless(HAS_NUMPY, "没有 numpy，频谱算不了")
class ComputeSpectrumTest(unittest.TestCase):
    def test_missing_file(self):
        self.assertEqual(core.compute_spectrum(os.path.join(tempfile.gettempdir(), "no.wav")),
                         (None, 0.0))

    def test_silence_has_no_dynamic_range(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.wav")
            make_wav(p, frames=16000, amp=0)
            level, fps = core.compute_spectrum(p)
            self.assertIsNone(level)
            self.assertEqual(fps, 0.0)

    def test_signal_produces_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.wav")
            make_wav(p, frames=16000, amp=14000)
            level, fps = core.compute_spectrum(p, bands=16, hop=0.04)
            self.assertIsNotNone(level)
            self.assertAlmostEqual(fps, 25.0, places=3)  # 1 / 0.04
            self.assertTrue(level)
            self.assertEqual(len(level[0]), 16)           # 每帧 16 个频带
            for row in level[:3]:
                self.assertTrue(all(0.0 <= v <= 1.0 for v in row))


if __name__ == "__main__":
    unittest.main()
