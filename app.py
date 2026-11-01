# -*- coding: utf-8 -*-
"""VocalithLoader 入口。

pywebview 负责窗口，界面在 ui/ 里，业务在 engine.py 里。
这一层只做三件事：开窗、把 Engine 的事件转给前端、把前端的调用转给 Engine。
"""

import json
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
# 一份是 exe 所在目录（放配置和输出），一份是内置资源目录（打包后解到临时目录）
RES = getattr(sys, "_MEIPASS", HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import core                      # noqa: E402
import engine as engine_mod      # noqa: E402

try:
    import webview
except Exception:
    webview = None


class Bridge:
    """Engine 的事件先入队，由前端定时来取。

    为什么不用 window.evaluate_js 直接推：WebView2 的控制器是 COM 对象，
    只能在 UI 线程碰，从引擎的后台线程调用会抛 InvalidCastException，
    异常被吞掉之后表现就是日志、监控全都不刷新。
    改成轮询之后跨线程问题从根上没了，代价是最多 120 毫秒的延迟。
    """

    # 同上：pywebview 会遍历 js_api 上的每个属性递归找可调用函数，
    # 这个对象用不着暴露给前端，标记一下让它别往里钻
    _serializable = False

    def __init__(self):
        self.queue = []
        self._lock = threading.Lock()

    def emit(self, kind, data):
        with self._lock:
            self.queue.append({"kind": kind, "data": data})
            if len(self.queue) > 3000:
                # 界面要是卡死没人来取，别让队列把内存吃光
                self.queue = self.queue[-1500:]

    def drain(self):
        with self._lock:
            out, self.queue = self.queue, []
        return out


class Api:
    def __init__(self, engine, bridge):
        self.engine = engine
        self.bridge = bridge
        # 下划线开头：pywebview 生成可调用函数清单时会直接跳过这种属性。
        # 不跳的话它会顺着 window.native 一路递归进 WinForms 的 COM 对象树，
        # 最后刷出一屏 InvalidCastException 和一个 RecursionError
        self._window = None

    # ── 状态 ────────────────────────────────────────────────
    def poll(self):
        """前端每 120 毫秒来取一次攒下的事件。"""
        return self.bridge.drain()

    def get_state(self):
        return self.engine.snapshot()

    def update_cfg(self, patch):
        return self.engine.update_cfg(patch)

    def refresh_models(self):
        return self.engine.refresh_models()

    def set_gsv_dir(self, path):
        return self.engine.set_gsv_dir(path)

    def auto_detect(self):
        return self.engine.auto_detect()

    # ── 服务 ────────────────────────────────────────────────
    def start_service(self):
        return self.engine.start_service()

    def takeover_service(self):
        return self.engine.takeover_service()

    def stop_service(self):
        return self.engine.stop_service()

    def apply_model(self):
        return self.engine.apply_model()

    def apply_ref(self):
        return self.engine.apply_ref()

    def bind_ref(self):
        return self.engine.bind_ref()

    # ── 合成 ────────────────────────────────────────────────
    def synth(self):
        return self.engine.synth()

    def get_presets(self):
        return self.engine.get_presets()

    def apply_preset(self, name):
        return self.engine.apply_preset(name)

    # ── 设备 ────────────────────────────────────────────────
    def device_state(self):
        return self.engine.device_state()

    def set_device(self, label):
        return self.engine.set_device(label)

    def get_monitor(self):
        return self.engine.monitor_payload()

    # ── 工具 ────────────────────────────────────────────────
    def self_check(self):
        return self.engine.self_check()

    def export_config(self):
        return self.engine.export_config()

    def import_config(self, text):
        return self.engine.import_config(text)

    def open_output(self):
        return self.engine.open_output()

    def open_in_explorer(self, path):
        return self.engine.open_in_explorer(path)

    def open_url(self, url):
        """在系统浏览器里打开一个网页。

        只放行 http/https：这个接口是给向导里「去下载」那个按钮用的，
        不该变成能启动任意本地程序的入口。
        """
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "msg": "只支持 http 或 https 地址"}
        try:
            import webbrowser
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": "打不开浏览器：%s" % e}

    def clear_history(self):
        return self.engine.clear_history()

    def batch_run(self):
        return self.engine.batch_run()

    # ── 波形 / 频谱 / 背景 ──────────────────────────────────
    def list_ref_audios(self):
        return self.engine.list_ref_audios()

    def wave_data(self, path):
        return self.engine.wave_data(path)

    def spectrum_data(self, path):
        return self.engine.spectrum_data(path)

    def bg_images(self):
        return self.engine.bg_images()

    def reset_bg(self):
        return self.engine.reset_bg_dir()

    def pick_bg_folder(self):
        try:
            import webview as wv
            picked = self._window.create_file_dialog(wv.FOLDER_DIALOG, allow_multiple=False)
        except Exception:
            return {"ok": False, "msg": "对话框打不开"}
        if not picked:
            return {"ok": False, "msg": "取消"}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        return self.engine.set_bg_dir(path)

    # ── 文件对话框 ──────────────────────────────────────────
    def pick_folder(self, kind="gsv"):
        try:
            import webview as wv
            picked = self._window.create_file_dialog(wv.FOLDER_DIALOG, allow_multiple=False)
        except Exception:
            return {"ok": False, "msg": "对话框打不开"}
        if not picked:
            return {"ok": False, "msg": "取消"}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        if kind == "gsv":
            return self.engine.set_gsv_dir(path)
        if kind == "assets":
            self.engine.cfg["assets_dir"] = path
            self.engine.save_config()
            return {"ok": True, "msg": "素材目录已设置", "path": path}
        return {"ok": True, "path": path}

    def pick_file(self, kind="ref"):
        try:
            import webview as wv
            picked = self._window.create_file_dialog(
                wv.OPEN_DIALOG, allow_multiple=False,
                file_types=("音频 (*.wav;*.mp3;*.flac)", "所有文件 (*.*)"))
        except Exception:
            return {"ok": False, "msg": "对话框打不开"}
        if not picked:
            return {"ok": False, "msg": "取消"}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        if kind == "ref":
            self.engine.cfg["ref_audio"] = path
            self.engine.save_config()
            return {"ok": True, "msg": "参考音频已选", "path": path}
        return {"ok": True, "path": path}

    def save_as(self):
        if not self.engine.last_wav or not os.path.isfile(self.engine.last_wav):
            return {"ok": False, "msg": "还没有生成过音频"}
        try:
            import webview as wv
            picked = self._window.create_file_dialog(
                wv.SAVE_DIALOG, save_filename=os.path.basename(self.engine.last_wav),
                file_types=("WAV (*.wav)", "MP3 (*.mp3)"))
        except Exception:
            return {"ok": False, "msg": "对话框打不开"}
        if not picked:
            return {"ok": False, "msg": "取消"}
        dest = picked if isinstance(picked, str) else picked[0]
        src = self.engine.last_wav
        try:
            if dest.lower().endswith(".mp3"):
                ff = os.path.join(self.engine.cfg.get("gsv_dir", ""), "runtime", "ffmpeg.exe")
                if not os.path.isfile(ff):
                    return {"ok": False, "msg": "找不到 ffmpeg.exe"}
                import subprocess
                subprocess.run([ff, "-y", "-loglevel", "error", "-i", src,
                                "-codec:a", "libmp3lame", "-b:a", "192k", dest], check=True)
            else:
                import shutil
                shutil.copyfile(src, dest)
            self.engine.log("已导出：%s" % dest)
            return {"ok": True, "msg": "已保存"}
        except Exception as e:
            return {"ok": False, "msg": "保存失败：%s" % e}

    def open_path(self, path):
        try:
            os.startfile(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}


def ui_path():
    return os.path.join(RES, "ui", "index.html")


def main():
    if webview is None:
        return 1
    bridge = Bridge()
    eng = engine_mod.Engine(emit=bridge.emit)
    api = Api(eng, bridge)

    sw = 1480
    sh = 920
    try:
        import tkinter as _tk
        r = _tk.Tk()
        sw = max(1180, min(1560, int(r.winfo_screenwidth() * 0.76)))
        sh = max(820, min(980, int(r.winfo_screenheight() * 0.80)))
        r.destroy()
    except Exception:
        pass

    window = webview.create_window(
        "VocalithLoader",
        url="file:///" + ui_path().replace("\\", "/"),
        js_api=api,
        width=sw, height=sh,
        min_size=(1180, 780),
        background_color="#0a0e13",
    )
    bridge.window = window
    api._window = window

    def startup():
        eng.start_monitor()
        # 第一次跑（或换了机器）配置是空的，自己找一遍便携包，省得用户先点浏览
        if not core.is_gsv_dir(eng.cfg.get("gsv_dir", "")):
            found = [p for p in core.detect_gsv(time_budget=6.0, log=eng.log)
                     if core.is_gsv_dir(p)]
            if found:
                eng.set_gsv_dir(found[0])
                bridge.emit("cfg", eng.snapshot()["cfg"])
            else:
                eng.log("没找到 GPT-SoVITS 便携包，需要先准备环境")
                # 第一次打开、电脑上又没有 GPT-SoVITS 的人，看到界面是懵的：
                # 程序能开，但什么都不发生。这里把「缺什么、多大、怎么装、装完
                # 什么样」一次讲完，而不是只丢一句「点浏览选目录」。
                bridge.emit("hint", {
                    "title": "还差一个 GPT-SoVITS 才能开始",
                    "body": (
                        "VocalithLoader 本身只是操作界面，真正干活的是另一个软件，"
                        "叫 GPT-SoVITS。它不在这个程序里，需要你另外准备。"
                        "<br><br>"
                        "<b>有多大</b>：官方整合包解压后大约 30 GB，"
                        "其中推理必需的部分约 13 GB。请先确认磁盘够用。"
                        "<br><br>"
                        "<b>怎么装</b>：<br>"
                        "1. 点下面的「打开下载页面」，在页面里找最新的整合包下载<br>"
                        "2. 下载下来是一个压缩包，右键选「解压到当前文件夹」<br>"
                        "3. 解压完打开那个文件夹，应该能直接看到 "
                        "<b>runtime</b> 文件夹和 <b>api_v2.py</b> 文件<br>"
                        "4. 回到这里点「选目录」，选那个文件夹"
                        "<br><br>"
                        "已经有的话，直接点「选目录」。"
                    ),
                    "okText": "打开下载页面",
                    "okAction": "download",
                    "url": "https://github.com/RVC-Boss/GPT-SoVITS/releases",
                    "cancelText": "选目录",
                    "cancelAction": "browse",
                })
        else:
            eng.refresh_models()
        bridge.emit("cfg", eng.snapshot()["cfg"])
        bridge.emit("models", eng.models)

        # 启动时就把「还能不能正常用」查一遍。以前这些毛病要拖到合成走到最后
        # 一步才暴露——输出目录不存在、requests 没加载都属于这类——报错位置
        # 离原因太远，用户看到的是一句看不懂的异常，而不是该去修什么。
        items = eng.self_check()
        blocking = [it[0] for it in items if len(it) > 3 and it[3] and not it[1]]
        # 目录都没指对的时候上面已经弹过提示了，这里不再叠一个
        if blocking and core.is_gsv_dir(eng.cfg.get("gsv_dir", "")):
            bridge.emit("hint", {
                "title": "有 %d 项要先处理" % len(blocking),
                "body": "自检发现的，不处理的话合成会失败：<br><br>"
                        + "<br>".join("· " + n for n in blocking)
                        + "<br><br>点顶上的「自检」看完整清单。",
            })

        eng.log("VocalithLoader 已就绪")

    window.events.loaded += lambda: threading.Thread(target=startup, daemon=True).start()

    try:
        webview.start()
    finally:
        try:
            eng.close()
        except Exception:
            pass
    return 0


def run_guarded():
    try:
        return main()
    except Exception:
        try:
            os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
            with open(os.path.join(HERE, "logs", "crash.log"), "a", encoding="utf-8") as f:
                f.write("\n===== %s =====\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                                   traceback.format_exc()))
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "启动失败，详见 logs\\crash.log",
                                             "VocalithLoader", 0x10)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(run_guarded())
