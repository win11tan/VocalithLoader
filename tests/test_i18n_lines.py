# -*- coding: utf-8 -*-
"""界面切英文后，日志和状态不该还留着中文。

这里把 engine 里实际会发出的那几句话逐条喂给 localize，
确认英文模式下翻得出来、中文模式下原样不动、翻不出来的不会崩。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


class LocalizeTest(unittest.TestCase):
    def test_log_lines(self):
        cases = [
            ("扫描到 GPT 3 个 / SoVITS 3 个",
             "Scanned 3 GPT weights and 3 SoVITS weights"),
            ("自检完成，全部通过", "Self-check passed"),
            ("VocalithLoader 已就绪", "VocalithLoader is ready"),
            ("启动服务 pid=23492，加载模型…",
             "Started the service, pid 23492, loading weights"),
            ("服务已停止", "Service stopped"),
            ("配置已导入", "Config imported"),
        ]
        for zh, want in cases:
            self.assertEqual(core.localize(zh, "en"), want, zh)

    def test_self_check_names(self):
        cases = [
            ("GPT-SoVITS 目录", "GPT-SoVITS folder"),
            ("输出目录", "Output folder"),
            ("日志目录", "Log folder"),
            ("参考音频", "Reference audio"),
            ("未设置", "not set"),
            ("端口 9880", "Port 9880"),
        ]
        for zh, want in cases:
            self.assertEqual(core.localize(zh, "en"), want, zh)

    def test_status_and_progress(self):
        cases = [
            ("加载中…", "Loading"),
            ("正在加载模型 0/4", "Loading weights 0 of 4"),
            ("加载超时", "Loading timed out"),
            ("合成中…", "Synthesising"),
            ("完成", "Done"),
        ]
        for zh, want in cases:
            self.assertEqual(core.localize(zh, "en"), want, zh)

    def test_parameters_are_kept(self):
        got = core.localize("自检：2 项需要处理（输出目录、参考音频）", "en")
        self.assertIn("2", got)
        self.assertIn("输出目录", got)  # 括号里的名字由调用方再翻，这里只验证外层
        got2 = core.localize("端口 9880 上已经有一个 GPT-SoVITS 服务（pid 4321），"
                             "不是本程序启动的", "en")
        self.assertIn("9880", got2)
        self.assertIn("4321", got2)

    def test_chinese_mode_untouched(self):
        for text in ("自检完成，全部通过", "加载中…", "扫描到 GPT 3 个 / SoVITS 3 个"):
            self.assertEqual(core.localize(text, "zh"), text)

    def test_unknown_text_survives(self):
        odd = "一条还没写翻译规则的日志"
        self.assertEqual(core.localize(odd, "en"), odd)
        self.assertEqual(core.localize("", "en"), "")

    def test_model_name(self):
        self.assertEqual(core.model_name("海伦娜", "en"), "Helena")
        self.assertEqual(core.model_name("企业", "en"), "Enterprise")
        self.assertEqual(core.model_name("企业2", "en"), "Enterprise 2")
        self.assertEqual(core.model_name("雪风", "en"), "Yukikaze")
        self.assertEqual(core.model_name("海伦娜", "zh"), "海伦娜")
        self.assertEqual(core.model_name("unknown", "en"), "unknown")

    def test_synthesis_progress(self):
        """合成进度条那行是 wait 和整句拼出来的，最容易漏。"""
        cases = [
            ("已完成 1/11 句 · 正在合成第 2 句（已等待 6 秒 / 预计 16 秒）",
             "1 of 11 lines done, synthesising line 2 (waited 6 s, about 16 s left)"),
            ("已完成 11/11 句（已等待 30 秒 / 预计 16 秒）",
             "11 of 11 lines done (waited 30 s, about 16 s left)"),
            ("已完成 3/5 句 · 正在合成第 4 句（已等待 12 秒）",
             "3 of 5 lines done, synthesising line 4 (waited 12 s)"),
            ("正在切分文本、提取特征…（已等待 2 秒）",
             "Splitting text and extracting features... (waited 2 s)"),
        ]
        for zh, want in cases:
            self.assertEqual(core.localize(zh, "en"), want, zh)

    def test_hardware_line_with_pieces(self):
        cases = [
            ("硬件：显卡 NVIDIA RTX 5060 Laptop ｜ 处理器 Core Ultra 9 275HX",
             "Hardware: GPU NVIDIA RTX 5060 Laptop | CPU Core Ultra 9 275HX"),
            ("硬件：未检测到独立显卡 ｜ 处理器 Core Ultra 9 275HX",
             "Hardware: no discrete GPU detected | CPU Core Ultra 9 275HX"),
            ("这段 12 字，显卡上预计 16 秒左右",
             "12 characters, about 16 seconds on the GPU"),
        ]
        for zh, want in cases:
            self.assertEqual(core.localize(zh, "en"), want, zh)

    def test_no_chinese_left_in_common_lines(self):
        """常见日志翻完之后不该再出现汉字。"""
        lines = [
            "扫描到 GPT 3 个 / SoVITS 3 个",
            "自检完成，全部通过",
            "服务就绪",
            "服务未启动",
            "正在停止服务 pid=100…",
            "模型已应用",
            "已生成 a.wav（3.20s / 耗时 5.10s）",
            "这段 12 字，显卡上预计 4 秒左右",
        ]
        for zh in lines:
            en = core.localize(zh, "en")
            self.assertFalse(any("\u4e00" <= c <= "\u9fff" for c in en),
                             "还有中文残留：%s -> %s" % (zh, en))


if __name__ == "__main__":
    unittest.main()
