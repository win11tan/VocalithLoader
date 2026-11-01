# -*- coding: utf-8 -*-
"""VocalithLoader 后端引擎。

v1 里这些逻辑都挂在 App 类上，和控件、tk 变量搅在一起。
这里只做一件事：把同样的行为搬到纯 Python 对象里，界面那边通过事件回调拿结果。

事件统一走 emit(kind, data)，kind 目前有：
    log       {line}                    一行日志
    status    {text, ok, busy}          顶栏状态
    progress  {value, text, mode}       进度（mode: determinate / indeterminate）
    models    {gpt, sovits}             扫描到的权重清单
    monitor   {cpu, gpu, cpu_name, gpu_name}
    history   {row}                     新生成一条
    toast     {text, kind}              轻提示
    state     {ready, busy, msg}
"""

import os
import re
import json
import random
import sys
import wave
import socket
import subprocess
import threading
import time
from collections import deque

import core

HERE_APP = os.path.dirname(os.path.abspath(__file__))
# 内置照片打包后在临时解包目录里，exe 同级找不到
RES_APP = getattr(sys, "_MEIPASS", HERE_APP)

requests = core.requests
LOG_DIR = core.LOG_DIR
OUTPUT_DIR = core.OUTPUT_DIR
CONFIG_PATH = core.CONFIG_PATH
LOAD_STEPS = core.LOAD_STEPS
LOAD_NAMES = core.LOAD_NAMES


class Engine:
    # pywebview 启动时会遍历 js_api 上的每个属性，遇到对象就往下递归去找可调用函数。
    # 这个实例是内部状态，不该被翻，标记一下让它停在门口
    _serializable = False

    def __init__(self, emit=None):
        self.emit = emit or (lambda kind, data: None)
        self.cfg = self.load_config()

        # 第一次运行时这两个目录都还不存在。把 exe 解压到一个新地方就是这种情况：
        # 以前只在启动服务时建了日志目录，输出目录一直没人建，于是合成会一路跑到
        # 最后一步写文件才抛 Errno 2，前面十几秒的推理全白费
        for _d in (LOG_DIR, OUTPUT_DIR):
            try:
                os.makedirs(_d, exist_ok=True)
            except OSError as e:
                self.log("建目录失败 %s: %s" % (_d, e))

        self.proc = None
        self.ready = False
        self.busy = False
        self.last_wav = None
        self.load_total = LOAD_STEPS
        self.load_done = 0
        self.load_names = []
        self.models = {"gpt": [], "sovits": []}
        self.model_map = {}
        self.gpu_ok = False
        self.gpu_info = None
        self.cpu_info = None
        self.gpu_proc = None
        self.gpu_name = ""
        self.cpu_name = core.cpu_name()
        self.psutil = None
        self.mon_cpu = deque(maxlen=90)
        self.mon_gpu = deque(maxlen=90)
        self.history = []
        self.prog_offset = None
        self.prog_err_offset = None
        self.prog_total = 1
        self._stop_mon = threading.Event()

    # ── 配置 ────────────────────────────────────────────────
    def load_config(self):
        cfg = dict(core.DEFAULT_CONFIG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
        if not cfg.get("batch_lines"):
            cfg["batch_lines"] = [list(x) for x in core.DEFAULT_BATCH_LINES]
        return cfg

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log("保存配置失败: %s" % e)

    def snapshot(self):
        """给前端的完整状态，界面加载时拉一次就够画出所有控件。"""
        c = self.cfg
        return {
            "cfg": {k: v for k, v in c.items() if k != "batch_lines"},
            "batch_lines": c.get("batch_lines", []),
            "ready": self.ready,
            "busy": self.busy,
            "last_wav": self.last_wav or "",
            "history": self.history[-200:],
            "models": self.models,
            "gpu_ok": self.gpu_ok,
            "gpu_name": self.gpu_name,
            "cpu_name": self.cpu_name,
            "load_total": self.load_total,
        }

    def update_cfg(self, patch):
        """前端改了什么就塞回来，只认配置里原本就有的键。"""
        for k, v in (patch or {}).items():
            if k in core.DEFAULT_CONFIG or k in ("profiles", "batch_lines", "assets_dir"):
                self.cfg[k] = v
        self.save_config()
        return self.snapshot()

    # ── 事件 ────────────────────────────────────────────────
    def _need_requests(self):
        """requests 是可选导入，缺了要在调接口前就说清楚，别拖到合成最后一步。"""
        if requests is None:
            raise RuntimeError(
                "requests 没能加载，合成用不了（%s）"
                % (getattr(core, "REQUESTS_IMPORT_ERROR", None) or "打包时缺依赖")
            )

    def log(self, msg):
        self.emit("log", {"line": "[%s] %s" % (time.strftime("%H:%M:%S"), msg)})

    def status(self, text, ok=False, busy=False):
        self.emit("status", {"text": text, "ok": ok, "busy": busy})

    def progress(self, value, text="", mode="determinate"):
        self.emit("progress", {"value": value, "text": text, "mode": mode})

    # ── 服务基础 ────────────────────────────────────────────
    def api_base(self):
        return "http://%s:%d" % (self.cfg["host"], int(self.cfg["port"]))

    def port_open(self, timeout=0.4):
        try:
            socket.create_connection((self.cfg["host"], int(self.cfg["port"])), timeout=timeout).close()
            return True
        except Exception:
            return False

    def probe_service(self):
        """端口有人听时，确认对方是不是 GPT-SoVITS。

        /tts 不带参数会走异常分支返回 500（text/plain），所以不能只认 400/422，
        最可靠的判据是响应头里的 server: uvicorn。
        """
        try:
            r = requests.get(self.api_base() + "/tts", timeout=3)
            server = (r.headers.get("server") or "").lower()
            ctype = (r.headers.get("content-type") or "").lower()
            if "uvicorn" in server:
                return True
            if r.status_code in (200, 400, 405, 422) and ("json" in ctype or "text/plain" in ctype):
                return True
            return False
        except Exception:
            return False

    def find_listener_pid(self, port=None):
        """谁在占着这个端口。拿不到就返回 0，别让统计本身把流程弄崩。"""
        port = int(port or self.cfg.get("port") or 9880)
        try:
            import psutil
            for c in psutil.net_connections(kind="inet"):
                if c.status == "LISTEN" and c.laddr and c.laddr.port == port:
                    return c.pid or 0
        except Exception:
            pass
        try:
            out = subprocess.run(["netstat", "-ano"], capture_output=True,
                                 text=True, timeout=10, errors="ignore").stdout
            for line in out.splitlines():
                if (":%d" % port) in line and "LISTENING" in line.upper():
                    tail = line.split()
                    if tail and tail[-1].isdigit():
                        return int(tail[-1])
        except Exception:
            pass
        return 0

    def kill_tree(self, pid):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
        except Exception:
            pass

    # ── 模型扫描 ────────────────────────────────────────────
    def scan_models(self):
        gsv = (self.cfg.get("gsv_dir") or "").strip()
        gpts, sovs = [], []
        if not os.path.isdir(gsv):
            return gpts, sovs
        try:
            for name in os.listdir(gsv):
                full = os.path.join(gsv, name)
                if not os.path.isdir(full):
                    continue
                low = name.lower()
                if not (low.startswith("gpt_weights") or low.startswith("sovits_weights")):
                    continue
                for f in os.listdir(full):
                    p = os.path.join(full, f)
                    if not os.path.isfile(p):
                        continue
                    lowf = f.lower()
                    if lowf.endswith(".ckpt"):
                        gpts.append((f, p))
                    elif lowf.endswith(".pth"):
                        sovs.append((f, p))
        except Exception as e:
            self.log("扫描模型失败: %s" % e)
        gpts.sort()
        sovs.sort()
        return gpts, sovs

    def refresh_models(self):
        gpts, sovs = self.scan_models()
        self.model_map = {}

        def pack(items):
            out = []
            for f, p in items:
                label = "%s  [%s]" % (f, os.path.basename(os.path.dirname(p)))
                self.model_map[label] = p
                out.append({"label": label, "path": p, "name": f})
            return out

        self.models = {"gpt": pack(gpts), "sovits": pack(sovs)}
        self.emit("models", self.models)
        self.log("扫描到 GPT %d 个 / SoVITS %d 个" % (len(gpts), len(sovs)))
        return self.models

    # ── 启动 / 停止服务 ─────────────────────────────────────
    def start_service(self):
        if self.proc and self.proc.poll() is None:
            self.log("服务已在运行")
            return {"ok": False, "msg": "服务已在运行"}
        gsv = (self.cfg.get("gsv_dir") or "").strip()
        py = os.path.join(gsv, "runtime", "python.exe")
        if not os.path.isfile(py):
            return {"ok": False, "msg": "未找到 runtime\\python.exe，请先选对 GPT-SoVITS 目录"}
        # 有显卡却在用 CPU 是最亏的一种情况：用户只会觉得慢，看不出问题出在哪
        if self.gpu_ok and core.read_device(gsv) == "cpu":
            self.log("注意：这台机器有显卡（%s），但配置里写的是 CPU 推理。"
                     "把「推理设备」切到显卡大约快 3~4 倍"
                     % (self.gpu_name or "独显"))
        if self.port_open():
            if self.probe_service():
                pid = self.find_listener_pid()
                self.ready = True
                self.status("服务就绪（已有实例）", ok=True)
                self.log("端口 %s 上已经有一个 GPT-SoVITS 服务（pid %s），不是本程序启动的"
                         % (self.cfg.get("port"), pid or "未知"))
                self.log("复用它读不到加载和合成的进度，条子只能按字数估；"
                         "想要准确的进度就点「接管并重启」")
                self.emit("state", {"ready": True, "busy": False, "msg": "复用现有服务"})
                return {"ok": True, "msg": "已复用现有服务", "reused": True,
                        "pid": pid, "port": self.cfg.get("port")}
            return {"ok": False, "msg": "端口 %s 被别的程序占用" % self.cfg["port"]}

        os.makedirs(LOG_DIR, exist_ok=True)
        out = open(os.path.join(LOG_DIR, "api_out.log"), "ab")
        err = open(os.path.join(LOG_DIR, "api_err.log"), "ab")
        cmd = [py, "-u", "api_v2.py", "-a", self.cfg["host"], "-p", str(self.cfg["port"]),
               "-c", "GPT_SoVITS/configs/tts_infer.yaml"]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # -u 和编码都要：stdout 重定向后默认块缓冲，进度要等缓冲区满才落盘；
        # 中文标记不钉成 utf-8 会按系统 GBK 写出去，客户端认不出来
        child_env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        try:
            self.proc = subprocess.Popen(cmd, cwd=gsv, stdout=out, stderr=err,
                                         creationflags=flags, env=child_env)
        except Exception as e:
            return {"ok": False, "msg": "启动失败：%s" % e}
        self.log("启动服务 pid=%d，加载模型…" % self.proc.pid)
        self.log("硬件：%s ｜ %s" % (
            ("显卡 " + self.gpu_name) if (self.gpu_ok and self.gpu_name) else "未检测到独立显卡",
            ("处理器 " + self.cpu_name) if self.cpu_name else "处理器"))
        self.status("加载中…", busy=True)
        try:
            self.load_offset = os.path.getsize(os.path.join(LOG_DIR, "api_out.log"))
        except Exception:
            self.load_offset = 0
        self.progress(0.0, "正在加载模型 0/%d" % LOAD_STEPS)
        self.emit("state", {"ready": False, "busy": True, "msg": "加载模型"})
        threading.Thread(target=self.watch_loading, daemon=True).start()
        threading.Thread(target=self.wait_ready, daemon=True).start()
        return {"ok": True, "msg": "服务启动中"}

    def takeover_service(self):
        """把端口上那个不是自己启动的服务关掉，再用这边拉一份起来。

        进度是从子进程的输出里数出来的，别人起的进程输出不经过我们，
        所以只有自己启动的那份才能给出真实进度。接管的代价是模型要重新加载一次。
        """
        port = int(self.cfg.get("port") or 9880)
        pid = self.find_listener_pid(port)
        if pid:
            self.log("接管服务：先结束端口 %d 上的进程 pid=%d" % (port, pid))
            self.kill_tree(pid)
            for _ in range(60):
                if not self.port_open():
                    break
                time.sleep(0.25)
        if self.port_open():
            return {"ok": False, "msg": "端口 %d 还占着，没能接管成功" % port}
        self.proc = None
        self.ready = False
        self.log("端口空出来了，用本程序的运行环境重新启动")
        return self.start_service()

    def watch_loading(self):
        """加载阶段的进度。

        分母不写死：服务端启动时把完整配置打出来，配置里有几个权重路径就加载几项。
        前面十几秒在初始化 torch 和 CUDA，一行日志都没有，完全不动会看着像死了，
        所以没新标记时让条子极缓慢地爬一点。
        """
        path = os.path.join(LOG_DIR, "api_out.log")
        offset = getattr(self, "load_offset", 0) or 0
        t0 = time.time()
        steps = 0
        total = LOAD_STEPS
        shown = 0.0
        names_seen = []
        for _ in range(900):
            if self.ready or self.proc is None:
                break
            time.sleep(0.2)
            # 睡这一下期间服务可能已经起来了，再推一次会把 100% 顶回去
            if self.ready or self.proc is None:
                break
            offset, n, conf, name = core.scan_load(path, offset)
            if conf > 0:
                total = max(1, min(12, conf))
            if n:
                steps += n
            if name and name not in names_seen:
                names_seen.append(name)
                self.load_names = list(names_seen)
            real = min(0.95, steps / float(total))
            if real > shown:
                shown = real
            else:
                shown = min(real + 0.15, shown + 0.0015)
            if steps >= total:
                text = "模型加载完毕，正在启动服务…（已等待 %.0f 秒）" % (time.time() - t0)
            elif name:
                text = "正在加载模型 %d/%d · %s（已等待 %.0f 秒）" % (
                    min(steps, total), total, LOAD_NAMES.get(name, name),
                    time.time() - t0)
            else:
                text = "正在加载模型 %d/%d（已等待 %.0f 秒）" % (
                    min(steps, total), total, time.time() - t0)
            self.progress(shown, text)
        self.load_total = total
        # steps 是日志里认出的标记次数，会多于实际权重数（同一个名字出现好几次），
        # 对外报的口径按权重个数来，不然会显示 27/4 这种
        self.load_done = min(steps, total)
        self.load_names = names_seen

    def wait_ready(self):
        for _ in range(180):
            if self.proc is None or self.proc.poll() is not None:
                self.status("服务已退出")
                self.progress(0.0, "", "indeterminate")
                self.log("服务退出，见 logs/api_err.log")
                self.emit("state", {"ready": False, "busy": False, "msg": "服务已退出"})
                return
            if self.port_open():
                self.ready = True
                self.status("服务就绪", ok=True)
                self.progress(1.0, "模型加载完成")
                threading.Timer(1.8, lambda: self.progress(0.0, "")).start()
                self.log("服务就绪：%s（本次加载权重 %d 项）" % (self.api_base(), self.load_total))
                self.emit("toast", {"text": "服务就绪", "kind": "ok"})
                self.emit("state", {"ready": True, "busy": False, "msg": "服务就绪"})
                return
            time.sleep(1)
        self.status("加载超时")
        self.progress(0.0, "", "indeterminate")
        self.log("加载超时，见 logs/api_err.log")
        self.emit("state", {"ready": False, "busy": False, "msg": "加载超时"})

    def stop_service(self):
        proc = self.proc
        self.proc = None
        self.ready = False
        self.status("正在停止…", busy=True)
        self.progress(0.0, "正在停止服务…", "indeterminate")
        self.emit("state", {"ready": False, "busy": True, "msg": "正在停止"})
        if proc is not None and proc.poll() is None:
            self.log("正在停止服务 pid=%d…" % proc.pid)
            threading.Thread(target=self._kill_worker, args=(proc,), daemon=True).start()
        elif self.port_open() and self.probe_service():
            # 端口上那份不是本程序拉起来的，这边停不了。以前这里直接报「已停止」，
            # 实际端口还开着，下次点启动又变成复用，越用越糊涂
            pid = self.find_listener_pid()
            self.ready = True
            self.log("端口 %s 上的服务（pid %s）不是本程序启动的，这边停不了它"
                     % (self.cfg.get("port"), pid or "未知"))
            self.log("想彻底关掉就去它自己的窗口里按 Ctrl+C；"
                     "想让它变成这边能管、能看进度的，点「启动服务」选接管")
            self.progress(0.0, "")
            self.status("服务就绪（外部实例）", ok=True)
            self.emit("state", {"ready": True, "busy": False, "msg": "外部服务未受影响"})
        else:
            self._after_stopped()
        return {"ok": True}

    def _kill_worker(self, proc):
        try:
            proc.terminate()
            proc.wait(timeout=6)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
            self.kill_tree(proc.pid)
        for _ in range(40):
            if not self.port_open():
                break
            time.sleep(0.25)
        self._after_stopped()

    def _after_stopped(self):
        self.ready = False
        self.progress(0.0, "")
        self.status("服务未启动")
        self.log("服务已停止")
        self.emit("state", {"ready": False, "busy": False, "msg": "已停止"})

    # ── 应用模型 / 参考 ─────────────────────────────────────
    def apply_model(self):
        if not self.ready:
            return {"ok": False, "msg": "请先启动服务"}
        gpt = self.cfg.get("gpt_path") or ""
        sov = self.cfg.get("sovits_path") or ""
        if not gpt or not sov:
            return {"ok": False, "msg": "请先选择 GPT 与 SoVITS 权重"}

        def work():
            # 换权重要让服务端把旧模型卸掉再读新的，两三秒起，给个提示别让人以为卡了
            self.progress(0, "正在应用模型…", "indeterminate")
            ok = False
            try:
                r1 = requests.get(self.api_base() + "/set_gpt_weights",
                                  params={"weights_path": gpt}, timeout=180)
                r2 = requests.get(self.api_base() + "/set_sovits_weights",
                                  params={"weights_path": sov}, timeout=180)
                self.log("GPT → %s (%d)" % (os.path.basename(gpt), r1.status_code))
                self.log("SoVITS → %s (%d)" % (os.path.basename(sov), r2.status_code))
                ok = r1.ok and r2.ok
                self.emit("model_now", {
                    "text": "当前：%s + %s" % (os.path.basename(gpt), os.path.basename(sov)),
                    "ok": ok,
                })
                self.emit("toast", {"text": "模型已应用" if ok else "模型应用失败",
                                    "kind": "ok" if ok else "err"})
            except Exception as e:
                self.log("应用模型失败: %s" % e)
                self.emit("toast", {"text": "应用模型失败", "kind": "err"})
            finally:
                self.progress(1.0, "模型已应用" if ok else "模型应用失败")
                time.sleep(0.5)
                self.progress(0.0, "")

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "msg": "正在应用"}

    def apply_ref(self):
        if not self.ready:
            return {"ok": False, "msg": "请先启动服务"}
        ref = self.cfg.get("ref_audio") or ""
        if not os.path.isfile(ref):
            return {"ok": False, "msg": "还没选参考音频，点「选择」挑一个 wav"}
        if not (self.cfg.get("prompt_text") or "").strip():
            self.log("提醒：参考文本为空，音色可能不准，建议填上与音频一致的文字")

        def work():
            try:
                r = requests.get(self.api_base() + "/set_refer_audio",
                                 params={"refer_audio_path": ref}, timeout=60)
                self.log("参考音频已应用 (%d)" % r.status_code)
                self.emit("toast", {"text": "参考音频已应用", "kind": "ok"})
            except Exception as e:
                self.log("应用参考失败: %s" % e)
                self.emit("toast", {"text": "应用参考失败", "kind": "err"})

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "msg": "正在应用"}

    # ── 绑定 / 预设 ─────────────────────────────────────────
    @staticmethod
    def profile_key(cfg):
        return "%s|%s" % (os.path.basename(cfg.get("gpt_path", "")),
                          os.path.basename(cfg.get("sovits_path", "")))

    def bind_ref(self):
        ref = self.cfg.get("ref_audio") or ""
        if not ref or not os.path.isfile(ref):
            return {"ok": False, "msg": "先选一条参考音频"}
        key = self.profile_key(self.cfg)
        self.cfg.setdefault("profiles", {})[key] = {
            "ref_audio": ref,
            "prompt_text": self.cfg.get("prompt_text", ""),
            "prompt_lang": self.cfg.get("prompt_lang", "ja"),
        }
        self.save_config()
        self.log("已绑定：%s" % key)
        return {"ok": True, "msg": "已绑定到当前模型"}

    def get_presets(self):
        """只列本机真绑定过的组合，不写死任何路径。"""
        gpts, sovs = self.scan_models()
        by_name = {}
        for f, p in gpts + sovs:
            by_name[os.path.basename(p)] = p
        out = []
        for key, prof in (self.cfg.get("profiles") or {}).items():
            if "|" not in key:
                continue
            g_name, s_name = key.split("|", 1)
            gp = by_name.get(g_name)
            sp = by_name.get(s_name)
            if not (gp and sp):
                continue
            ref = (prof.get("ref_audio") or "").strip()
            if ref and not os.path.isfile(ref):
                continue
            out.append({
                "name": os.path.splitext(g_name)[0],
                "gpt": gp, "sovits": sp, "ref": ref,
                "text": prof.get("prompt_text", ""),
                "lang": prof.get("prompt_lang", "ja"),
            })
        out.sort(key=lambda x: x["name"].lower())
        return out

    def apply_preset(self, name):
        for p in self.get_presets():
            if p["name"] == name:
                self.cfg.update({"gpt_path": p["gpt"], "sovits_path": p["sovits"],
                                 "ref_audio": p["ref"], "prompt_text": p["text"],
                                 "prompt_lang": p["lang"]})
                self.save_config()
                self.log("已套用组合：%s" % name)
                self.emit("cfg", self.snapshot()["cfg"])
                return {"ok": True, "msg": "已套用 %s" % name}
        return {"ok": False, "msg": "找不到这个组合"}

    # ── 合成 ────────────────────────────────────────────────
    def estimate_seconds(self, text):
        """按字数粗估合成要多久，只用来给个心理预期。

        实测这台机器（24 核 / RTX 5060）上：显卡每秒出十五字上下，
        纯 CPU 每秒四字上下，差三到四倍。别的机器会慢些，量级是对的。
        """
        chars = max(1, len(text or ""))
        dev = core.read_device(self.cfg.get("gsv_dir") or "")
        return chars * (0.07 if dev == "cuda" else 0.26) + 2.0

    def synth(self):
        if self.busy:
            return {"ok": False, "msg": "正在合成"}
        if not self.ready:
            return {"ok": False, "msg": "请先启动服务"}
        cfg = self.cfg
        text = (cfg.get("text") or "").strip()
        warn = core.check_text(text)
        if warn and ("为空" in warn or "没有可发音" in warn):
            return {"ok": False, "msg": warn}
        if warn:
            self.log(warn)
        ref = cfg.get("ref_audio") or ""
        if not os.path.isfile(ref):
            # 一条都没有就直接拒绝太狠了：参考音频只负责借语气，
            # 音色是权重里学到的，手头只要有干净人声就能跑起来
            cands = self.list_ref_audios()
            if cands:
                ref = cands[0]["path"]
                self.cfg["ref_audio"] = ref
                self.save_config()
                self.log("参考音频还没选，先拿 %s 顶上（五秒以上、干净人声就行）"
                         % os.path.basename(ref))
                self.emit("cfg", self.snapshot()["cfg"])
            else:
                return {"ok": False, "msg": "一段参考音频都没找到。"
                                            "参考音频只是一段 3 到 10 秒的干净人声，"
                                            "不一定是角色本人的声音，随便一段录音放进 "
                                            "GPT-SoVITS 目录里再点「浏览…」选中即可。"}

        # 时长这道坎必须自己先查：GPT-SoVITS 只认 3~10 秒，短了直接 400，
        # 而它返回的 400 只有一句 Bad Request，不说为什么，用户根本猜不到
        ref_dur = self._wav_dur(ref)
        if ref_dur and not (2.9 <= ref_dur <= 10.1):
            same = [x for x in self.list_ref_audios()
                    if x.get("model") and x["model"].lower() == (
                        (cfg.get("gpt_path") or "").split("\\")[-1].split("-")[0].lower())]
            alt = sorted(same, key=lambda x: abs((x.get("dur") or 0) - 5))[0] if same else None
            hint = ("我把这个角色自己的样本换上去？「%s」%.1f 秒，点一下就好"
                    % (alt.get("scene") or alt.get("no") or "样本", alt.get("dur") or 0)) if alt else ""
            return {"ok": False,
                    "msg": "参考音频时长 %.2f 秒，GPT-SoVITS 只接受 3~10 秒，所以被服务端拒了。"
                           "换一条五秒左右的干净人声。%s" % (ref_dur, hint),
                    "suggest_ref": alt.get("path") if alt else ""}

        seed = cfg.get("seed", 42)
        if cfg.get("random_seed"):
            seed = random.randint(0, 999999)

        payload = {
            "text": text, "text_lang": cfg["text_lang"],
            "ref_audio_path": ref,
            "prompt_text": cfg.get("prompt_text", ""), "prompt_lang": cfg["prompt_lang"],
            "top_k": int(cfg["top_k"]), "top_p": float(cfg["top_p"]),
            "temperature": float(cfg["temperature"]),
            "text_split_method": cfg["text_split_method"],
            "repetition_penalty": float(cfg["repetition_penalty"]),
            "seed": int(seed), "media_type": "wav", "streaming_mode": False,
        }

        self.busy = True
        self.status("合成中…", busy=True)
        est = self.estimate_seconds(text)
        self.prog_est = est
        on_gpu = core.read_device(self.cfg.get("gsv_dir") or "") == "cuda"
        # CPU 上这一段要跑好几分钟，先说个大概，不然用户只能干等着猜
        self.log("这段 %d 字，%s上预计 %s"
                 % (len(text), "显卡" if on_gpu else "处理器",
                    ("%d 秒左右" % est) if est < 90 else ("%d 分 %d 秒左右" % (int(est) // 60, int(est) % 60))))
        # 服务是自己启的才有日志可数；复用外部实例时没有日志，退回来回跑
        self.prog_offset = None
        self.prog_err_offset = None
        self.prog_total = core.count_sentences(text)
        self.prog_chars = len(text)
        if self.proc is not None:
            for attr, name in (("prog_offset", "api_out.log"), ("prog_err_offset", "api_err.log")):
                try:
                    setattr(self, attr, os.path.getsize(os.path.join(LOG_DIR, name)))
                except Exception:
                    setattr(self, attr, 0)
        if self.prog_offset is not None:
            self.progress(0.0, "已完成 0/%d 句" % self.prog_total)
            threading.Thread(target=self.watch_progress, daemon=True).start()
        else:
            # 服务不是自己起的就摸不到它的输出，只能按句数和这台机器的速度估
            self.progress(0.05, "正在合成 %d 句…（估算）" % self.prog_total)
            threading.Thread(target=self.watch_estimate, daemon=True).start()
        self.emit("state", {"ready": True, "busy": True, "msg": "合成中"})
        t0 = time.time()

        def work():
            try:
                self._need_requests()
                r = requests.post(self.api_base() + "/tts", json=payload, timeout=600)
                if r.status_code != 200:
                    # 服务端把真正的原因写在 body 里（比如"参考音频在3~10秒范围外"），
                    # raise_for_status 只给一句 Bad Request，等于白跑一趟
                    detail = ""
                    try:
                        body = r.json()
                        detail = body.get("Exception") or body.get("message") or ""
                    except Exception:
                        detail = (r.text or "")[:200]
                    raise RuntimeError("服务端拒绝（%d）：%s" % (r.status_code, detail or "没给原因"))
                stem = time.strftime("%Y%m%d_%H%M%S") + "_" + core.safe_filename(text)
                # 万一运行过程中目录被删了，别等到写完才发现
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                path = core.unique_path(OUTPUT_DIR, stem)
                with open(path, "wb") as f:
                    f.write(r.content)
                dur = core.fmt_duration(path)
                cost = time.time() - t0
                row = {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "text": text,
                    "dur": round(dur, 2),
                    "file": os.path.basename(path),
                    "path": path,
                    "seed": seed,
                    "cost": round(cost, 1),
                }
                self.last_wav = path
                self.history.append(row)
                self.emit("history", row)
                self.emit("toast", {"text": "已生成 %s" % os.path.basename(path), "kind": "ok"})
                self.log("已生成 %s（%.2fs / 耗时 %.1fs）" % (os.path.basename(path), dur, cost))
            except Exception as e:
                self.log("合成失败: %s" % e)
                self.emit("toast", {"text": "合成失败", "kind": "err"})
            finally:
                self.busy = False
                self.progress(1.0, "完成")
                self.status("服务就绪", ok=True)
                self.emit("state", {"ready": self.ready, "busy": False, "msg": "合成结束"})
                # 让满格停一下再清空，否则合成成功也看不出到底跑完了没有
                time.sleep(0.8)
                self.progress(0.0, "")

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "msg": "开始合成"}

    def watch_progress(self):
        """两处日志拼出真实进度：out 数句子，err 数句内 token。"""
        out_path = os.path.join(LOG_DIR, "api_out.log")
        err_path = os.path.join(LOG_DIR, "api_err.log")
        offset = self.prog_offset or 0
        err_offset = self.prog_err_offset or 0
        total = max(1, self.prog_total)
        done = 0
        inside = 0.0
        best = 0.0
        t0 = time.time()
        for _ in range(3600):
            if not self.busy:
                break
            time.sleep(0.15)
            if not self.busy:
                break
            offset, n = core.read_progress(out_path, offset)
            if n:
                done += n
                inside = 0.0
            err_offset, frac = core.read_tqdm(err_path, err_offset)
            if frac is not None:
                inside = frac
            value = (done + max(0.0, min(1.0, inside))) / float(total)
            value = max(best, min(0.995, value))
            best = value
            wait = "（已等待 %.0f 秒）" % (time.time() - t0)
            est = getattr(self, "prog_est", 0) or 0
            if est:
                wait = "（已等待 %.0f 秒 / 预计 %s）" % (
                    time.time() - t0,
                    ("%d 秒" % est) if est < 90 else ("%d 分 %d 秒" % (int(est) // 60, int(est) % 60)))
            if done >= total:
                text = "已完成 %d/%d 句%s" % (total, total, wait)
            elif done == 0 and value < 0.005:
                text = "正在切分文本、提取特征…%s" % wait
            else:
                text = "已完成 %d/%d 句 · 正在合成第 %d 句%s" % (
                    done, total, done + 1, wait)
            self.progress(value, text)

    def watch_estimate(self):
        """复用外部启动的服务时的进度。

        那个实例的输出不在我们手里，读不到 token 到第几个，只能按字数和
        这台机器的速度往前推。估得不一定准，但至少能看出还在跑、快到头了。
        """
        total = max(1, self.prog_total)
        # 这台机器上实测 GPU 每秒能出十个字上下，CPU 慢三倍左右
        speed = 10.0 if self.gpu_ok else 3.5
        chars = max(1, getattr(self, "prog_chars", 0))
        span = max(3.0, chars / speed)
        t0 = time.time()
        shown = 0.05
        while self.busy:
            time.sleep(0.2)
            # 睡这一下期间可能已经出结果了，别再往前推，否则会把 100% 顶回去
            if not self.busy:
                break
            v = min(0.94, (time.time() - t0) / span)
            if v > shown:
                shown = v
                self.progress(shown, "正在合成 %d 句…估算 %d%%（已等待 %.0f 秒，外部服务看不到细节）"
                              % (total, int(shown * 100), time.time() - t0))

    # ── 设备 ────────────────────────────────────────────────
    def device_state(self):
        gsv = self.cfg.get("gsv_dir") or ""
        dev = core.read_device(gsv) if os.path.isdir(gsv) else "cuda"
        label = {"cuda": "显卡 GPU", "cpu": "处理器 CPU"}.get(dev, "自动")
        return {"device": dev, "label": label, "gpu_ok": self.gpu_ok,
                "cpu_name": self.cpu_name, "gpu_name": self.gpu_name}

    def set_device(self, label):
        gsv = self.cfg.get("gsv_dir") or ""
        dev = core.DEVICE_VALUES.get(label, "auto")
        if dev == "auto":
            dev = "cuda" if self.gpu_ok else "cpu"
        if dev == "cuda" and not self.gpu_ok:
            return {"ok": False, "msg": "没检测到独立显卡，只能用处理器"}
        ok, msg = core.write_device(gsv, dev)
        if ok:
            self.log("推理设备写为 %s，下次启动服务生效" % dev)
            self.cfg["device"] = dev
            self.save_config()
            return {"ok": True, "msg": "已切到 %s，重启服务生效" % ("显卡" if dev == "cuda" else "处理器")}
        return {"ok": False, "msg": msg}

    # ── 系统监控 ────────────────────────────────────────────
    def start_monitor(self):
        try:
            import psutil
            self.psutil = psutil
            psutil.cpu_percent(None)
        except Exception:
            self.psutil = None
        self.gpu_ok = core.gpu_available()
        if self.gpu_ok:
            threading.Thread(target=self._gpu_reader, daemon=True).start()
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _gpu_reader(self):
        """常驻一个 nvidia-smi 让它自己循环吐数据。

        每次起一个进程要半秒，一秒一次光监控就把机器拖垮了。
        """
        cmd = ["nvidia-smi",
               "--query-gpu=name,utilization.gpu,clocks.current.graphics,"
               "memory.used,memory.total,temperature.gpu",
               "--format=csv,noheader,nounits", "-l", "2"]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    creationflags=flags, text=True, bufsize=1)
        except Exception:
            return
        self.gpu_proc = proc
        try:
            for line in proc.stdout:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    gname = parts[0]
                    if gname and not self.gpu_name:
                        self.gpu_name = core.short_name(gname)
                    try:
                        self.gpu_info = tuple(int(float(p)) for p in parts[1:6])
                    except ValueError:
                        pass
        except Exception:
            pass

    def _monitor_loop(self):
        while not self._stop_mon.is_set():
            try:
                if self.psutil is not None:
                    pct = self.psutil.cpu_percent(None)
                    freq = self.psutil.cpu_freq()
                    self.cpu_info = (pct, freq.current if freq else 0.0)
                    self.mon_cpu.append(pct)
                if self.gpu_info is not None:
                    self.mon_gpu.append(self.gpu_info[0])
                elif self.gpu_ok:
                    self.mon_gpu.append(0.0)
                self.emit("monitor", self.monitor_payload())
            except Exception:
                pass
            self._stop_mon.wait(1.0)

    def monitor_payload(self):
        cpu = self.cpu_info or (0.0, 0.0)
        gpu = self.gpu_info
        return {
            "cpu": {"pct": round(cpu[0], 0), "mhz": round(cpu[1], 0),
                    "name": self.cpu_name or "处理器",
                    "hist": list(self.mon_cpu)[-60:]},
            "gpu": ({"pct": gpu[0], "ghz": round(gpu[1] / 1000.0, 2),
                     "temp": gpu[4], "mem": round(gpu[2] / 1024.0, 1),
                     "total": round(gpu[3] / 1024.0, 1),
                     "name": self.gpu_name or "显卡",
                     "hist": list(self.mon_gpu)[-60:]} if gpu else None),
            "gpu_ok": self.gpu_ok,
        }

    def stop_monitor(self):
        self._stop_mon.set()
        try:
            if self.gpu_proc is not None:
                self.gpu_proc.kill()
        except Exception:
            pass

    # ── 自检 / 配置导入导出 ─────────────────────────────────
    def _dir_writable(self, path):
        """真的往里写个文件试试。Windows 上 os.access 对权限的判断不可靠。"""
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".vocalith_write_test")
            with open(probe, "wb") as f:
                f.write(b"1")
            os.remove(probe)
            return True
        except OSError:
            return False

    def self_check(self):
        """返回 [名称, 是否正常, 说明, 是否必需]。

        第四项是必需标记。出问题要拦住人的才标 True；像 ffmpeg 缺了只是不能
        导 mp3，不该让第一次打开的人以为整个程序坏了。
        """
        gsv = (self.cfg.get("gsv_dir") or "").strip()
        out_ok = self._dir_writable(OUTPUT_DIR)
        log_ok = self._dir_writable(LOG_DIR)

        # 只有跑源码才关心解释器版本，打成 exe 之后用的是自带的那份
        frozen = getattr(sys, "frozen", False)
        py_ok = bool(frozen) or sys.version_info >= (3, 9)

        req_err = getattr(core, "REQUESTS_IMPORT_ERROR", None)

        items = [
            ("GPT-SoVITS 目录", core.is_gsv_dir(gsv), gsv or "未设置", True),
            ("runtime\\python.exe",
             os.path.isfile(os.path.join(gsv, "runtime", "python.exe")),
             "运行推理子进程用", True),
            ("requests 模块", requests is not None,
             "HTTP 请求" if requests is not None else ("加载失败：%s" % (req_err or "原因未知")),
             True),
            ("输出目录", out_ok, OUTPUT_DIR, True),
            ("日志目录", log_ok, LOG_DIR, True),
            ("端口 %s" % self.cfg.get("port"),
             not self.port_open() or self.probe_service(),
             "空闲" if not self.port_open() else "被占用", True),
            ("GPT 权重", bool(self.cfg.get("gpt_path")), self.cfg.get("gpt_path") or "未设置", True),
            ("SoVITS 权重", bool(self.cfg.get("sovits_path")), self.cfg.get("sovits_path") or "未设置", True),
            ("参考音频", os.path.isfile(self.cfg.get("ref_audio") or ""),
             self.cfg.get("ref_audio") or "未设置", True),
            ("Python 版本", py_ok,
             "打包运行，不适用" if frozen else "%d.%d" % sys.version_info[:2], True),
            ("ffmpeg", os.path.isfile(os.path.join(gsv, "runtime", "ffmpeg.exe")),
             "导出 mp3 用，缺了不影响合成", False),
        ]

        bad = [n for n, ok, _, req in items if req and not ok]
        if bad:
            self.log("自检：%d 项需要处理（%s）" % (len(bad), "、".join(bad)))
        else:
            self.log("自检完成，全部通过")
        return items

    def export_config(self):
        return {"ok": True, "data": json.dumps(self.cfg, ensure_ascii=False, indent=2)}

    def import_config(self, text):
        try:
            data = json.loads(text)
        except Exception as e:
            return {"ok": False, "msg": "不是合法的 JSON：%s" % e}
        if not isinstance(data, dict):
            return {"ok": False, "msg": "内容不是配置对象"}
        self.cfg.update({k: v for k, v in data.items() if k in core.DEFAULT_CONFIG
                         or k in ("profiles", "batch_lines", "assets_dir")})
        self.save_config()
        self.refresh_models()
        self.log("配置已导入")
        return {"ok": True, "msg": "配置已导入", "snapshot": self.snapshot()}

    def set_gsv_dir(self, path):
        if not core.is_gsv_dir(path):
            return {"ok": False, "msg": "这个目录不像 GPT-SoVITS 便携包"}
        self.cfg["gsv_dir"] = path
        self.save_config()
        self.refresh_models()
        self.emit("cfg", self.snapshot()["cfg"])
        self.log("GPT-SoVITS 目录：%s" % path)
        return {"ok": True, "msg": "目录已设置", "models": self.models}

    def auto_detect(self):
        found = core.detect_gsv(time_budget=8.0, log=self.log)
        return {"ok": bool(found), "found": found}

    # ── 批量替换 ────────────────────────────────────────────
    def batch_run(self):
        if not self.ready:
            return {"ok": False, "msg": "请先启动服务"}
        rows = [(n, t) for n, t in self.cfg.get("batch_lines", []) if t]
        if not rows:
            return {"ok": False, "msg": "批量台词是空的，先点「编辑台词」"}
        assets = self.cfg.get("assets_dir") or ""
        if not os.path.isdir(assets):
            return {"ok": False, "msg": "还没选要替换的素材目录"}
        ff = os.path.join(self.cfg.get("gsv_dir", ""), "runtime", "ffmpeg.exe")
        if not os.path.isfile(ff):
            return {"ok": False, "msg": "缺 ffmpeg.exe，导 mp3 用"}

        def work():
            import shutil
            bak = os.path.join(assets, "_bak_original")
            os.makedirs(bak, exist_ok=True)
            done = 0
            cfg = self.cfg
            for name, text in rows:
                try:
                    payload = {
                        "text": text, "text_lang": cfg["text_lang"],
                        "ref_audio_path": cfg.get("ref_audio", ""),
                        "prompt_text": cfg.get("prompt_text", ""),
                        "prompt_lang": cfg.get("prompt_lang", "ja"),
                        "top_k": int(cfg["top_k"]), "top_p": float(cfg["top_p"]),
                        "temperature": float(cfg["temperature"]),
                        "text_split_method": cfg["text_split_method"],
                        "repetition_penalty": float(cfg["repetition_penalty"]),
                        "seed": int(cfg["seed"]), "media_type": "wav", "streaming_mode": False,
                    }
                    self._need_requests()
                    r = requests.post(self.api_base() + "/tts", json=payload, timeout=600)
                    r.raise_for_status()
                    safe = core.safe_filename(name, 60)
                    wav = core.unique_path(OUTPUT_DIR, "_batch_" + safe)
                    with open(wav, "wb") as f:
                        f.write(r.content)
                    mp3 = os.path.join(assets, safe + ".mp3")
                    keep = os.path.join(bak, safe + ".mp3")
                    if os.path.isfile(mp3) and not os.path.isfile(keep):
                        shutil.copyfile(mp3, keep)
                    subprocess.run([ff, "-y", "-loglevel", "error", "-i", wav,
                                    "-codec:a", "libmp3lame", "-b:a", "192k", mp3], check=True)
                    done += 1
                    self.log("已替换 %s.mp3" % name)
                except Exception as e:
                    self.log("替换 %s 失败: %s" % (name, e))
            self.log("批量完成 %d/%d，原件备份在 _bak_original" % (done, len(rows)))
            self.emit("toast", {"text": "批量完成 %d/%d" % (done, len(rows)),
                                "kind": "ok" if done == len(rows) else "err"})

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "msg": "开始替换 %d 条" % len(rows)}

    # ── 参考音频清单 ────────────────────────────────────────
    # 训练样本的文件名里多半带着这句语音的场合。参考音频决定的是语气，
    # 所以「战斗」「礼物」这类标签比一串路径有用得多，统一翻成中文。
    SCENE_ZH = (
        ("battle", "战斗"), ("gift", "礼物"), ("home", "主界面"),
        ("login", "登录"), ("touch", "触摸"), ("head", "摸头"),
        ("skill", "技能"), ("attack", "攻击"), ("alarm", "警报"),
        ("warn", "警告"), ("hit", "受击"), ("damage", "受击"),
        ("destroyed", "击破"), ("death", "击破"), ("launch", "起飞"),
        ("capture", "占领"), ("mission", "任务"), ("idle", "待机"),
        ("levelup", "升级"), ("level_up", "升级"), ("like", "好感"),
        ("wedding", "誓约"), ("profile", "档案"), ("mail", "邮件"),
        ("email", "邮件"), ("expedition", "委托"), ("vote", "投票"),
        ("start", "开始"), ("end", "结束"), ("win", "胜利"),
        ("lose", "失败"),
    )

    # 认识的模型给个中文名，不认识的照原样显示，不会瞎猜
    MODEL_ZH = {
        "helena": "海伦娜",
        "yukikaze": "雪风",
        "enterprise": "企业",
        "enterprise2": "企业2",
    }

    @staticmethod
    def _sample_base(fn):
        """剥掉切片尾巴，留下原本的句名。

        cv-30116-battle_1.wav_0000000000_0000111360.wav
        → cv-30116-battle_1
        """
        base = re.sub(r"\.wav_\d+_\d+\.wav$", "", fn, flags=re.I)
        if base.lower().endswith(".wav"):
            base = base[:-4]
        return base

    @staticmethod
    def _scene_of(fn):
        """从句名看出这句是什么场合的语音，看不出来就返回空。

        手上的命名有两种：
            cv-30116-battle_1.wav_0000000000_0000111360.wav
            Enterprise_Speech_Alarms_Fire_Alarm.wav
        """
        base = Engine._sample_base(fn)
        m = re.match(r"^cv-\d+-(.+?)_\d+$", base, flags=re.I)
        if m:
            word = m.group(1)
        else:
            m = re.search(r"_speech_(.+)$", base, flags=re.I)
            if not m:
                return ""
            word = m.group(1)
        low = word.lower()
        for key, zh in Engine.SCENE_ZH:
            if key in low:
                return zh
        return ""

    @staticmethod
    def _voice_no(fn):
        """没有场合信息时，至少给个编号好区分。
        cv-10205-10.wav_...  → 第10条
        cv-30116-battle_1.wav_... → 第1条
        """
        base = Engine._sample_base(fn)
        m = re.match(r"^cv-\d+[-_](\d+)$", base, flags=re.I)
        if m:
            return "第%s条" % m.group(1)
        m = re.match(r"^cv-\d+-.+?_(\d+)$", base, flags=re.I)
        if m:
            return "第%s条" % m.group(1)
        return ""

    @staticmethod
    def model_zh(name):
        return Engine.MODEL_ZH.get((name or "").lower(), name or "")

    @staticmethod
    def _wav_dur(path):
        try:
            with wave.open(path, "rb") as w:
                return round(w.getnframes() / float(w.getframerate()), 1)
        except Exception:
            return 0.0

    def scan_training_refs(self):
        """从训练日志里取参考音频。

        GPT-SoVITS 训练时会把每条音频切片放进 logs/<模型名>/5-wav32k，
        对应的原文写在 2-name2text.txt 里。这俩本来就是配好对的，
        拿来当参考音频正合适，也不用用户自己再去找素材。
        """
        gsv = (self.cfg.get("gsv_dir") or "").strip()
        logs = os.path.join(gsv, "logs")
        out = []
        if not os.path.isdir(logs):
            return out
        for name in sorted(os.listdir(logs)):
            d = os.path.join(logs, name)
            if not os.path.isdir(d):
                continue
            wav_dir = os.path.join(d, "5-wav32k")
            txt_path = os.path.join(d, "2-name2text.txt")
            if not (os.path.isdir(wav_dir) and os.path.isfile(txt_path)):
                continue
            texts = {}
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.rstrip(chr(10)).split(chr(9))
                        if len(parts) >= 4 and parts[3].strip():
                            texts[parts[0]] = parts[3].strip()
            except Exception:
                continue
            cands = []
            try:
                files = sorted(os.listdir(wav_dir))
            except OSError:
                continue
            for fn in files:
                if not fn.lower().endswith(".wav"):
                    continue
                text = texts.get(fn)
                if not text:
                    continue
                dur = self._wav_dur(os.path.join(wav_dir, fn))
                if 2.5 <= dur <= 9.0:
                    cands.append((dur, fn, text, self._scene_of(fn),
                                  self._voice_no(fn)))
            # 能看出场合的排前面，其次才看是不是接近五秒：
            # 太短音色拿不准，太长每次合成都要等它跑完
            cands.sort(key=lambda x: (0 if x[3] else 1, abs(x[0] - 5.0)))
            # 同一种场合最多留两条，免得六条全是 battle_1..6；
            # 光有编号的样本互相不算同一种，各留各的
            picked = []
            per = {}
            for dur, fn, text, scene, no in cands:
                key = scene or fn
                if scene and per.get(key, 0) >= 2:
                    continue
                per[key] = per.get(key, 0) + 1
                picked.append((dur, fn, text, scene, no))
                if len(picked) >= 6:
                    break
            for dur, fn, text, scene, no in picked:
                out.append({
                    "path": os.path.join(wav_dir, fn),
                    "name": fn,
                    "dir": "%s 训练样本" % name,
                    "dur": dur,
                    "text": text,
                    "scene": scene,
                    "no": no,
                    "lang": "ja",
                    "model": name,
                    "model_zh": self.model_zh(name),
                })
        return out

    def list_ref_audios(self):
        """把几个常见位置里的参考音频都找出来。

        以前界面上只有配置里那一条，换角色就得自己去翻硬盘。
        扫描范围：GPT-SoVITS 根目录、当前参考音频所在目录、权重目录及其父目录。
        """
        gsv = (self.cfg.get("gsv_dir") or "").strip()
        dirs = []
        if gsv:
            dirs.append(gsv)
        cur = (self.cfg.get("ref_audio") or "").strip()
        if cur:
            d = os.path.dirname(cur)
            if d:
                dirs.append(d)
        for sub in ("GPT_weights_v2Pro", "GPT_weights_v2", "GPT_weights_v3",
                    "SoVITS_weights_v2Pro", "SoVITS_weights_v2", "SoVITS_weights_v3"):
            p = os.path.join(gsv, sub)
            if os.path.isdir(p):
                dirs.append(p)
                dirs.append(os.path.dirname(p))
        seen_dir, seen_file = set(), set()
        out = self.scan_training_refs()
        for it in out:
            seen_file.add(it["path"])
        for d in dirs:
            d = os.path.normpath(d)
            if not os.path.isdir(d) or d in seen_dir:
                continue
            seen_dir.add(d)
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for n in names:
                if not n.lower().endswith((".wav", ".mp3", ".flac")):
                    continue
                full = os.path.join(d, n)
                if full in seen_file or not os.path.isfile(full):
                    continue
                seen_file.add(full)
                out.append({"path": full, "name": n,
                            "dir": os.path.basename(d),
                            "dur": self._wav_dur(full),
                            "text": "", "scene": "", "no": "",
                            "model": "", "model_zh": ""})
        # 训练样本排前面：它自带原文和场合，是首选；零散的通用音频垫在后面。
        # 以前一律按文件名排，通用音频里也有同名的 cv-xxx 文件，会把样本挤到中间去
        out.sort(key=lambda x: (0 if x.get("model") else 1, x["name"].lower()))
        return out

    # ── 波形 / 频谱 / 背景图 ────────────────────────────────
    def wave_data(self, path):
        """峰值给前端画波形，前端不做解码，省得 WebView 里 file:// 被拦。"""
        if not path or not os.path.isfile(path):
            return []
        return core.read_peaks(path, 140)

    def spectrum_data(self, path):
        if not path or not os.path.isfile(path):
            return {"level": [], "fps": 0}
        level, fps = core.compute_spectrum(path)
        return {"level": level or [], "fps": fps}

    def bg_images(self):
        """内置照片的完整路径，前端拿去做轮播。"""
        folder = self.cfg.get("bg_dir") or os.path.join(RES_APP, "bg_builtin")
        exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        return [os.path.join(folder, n) for n in names if n.lower().endswith(exts)]

    def set_bg_dir(self, path):
        if not os.path.isdir(path):
            return {"ok": False, "msg": "目录不存在"}
        self.cfg["bg_dir"] = path
        self.save_config()
        return {"ok": True, "msg": "背景图目录已换", "images": self.bg_images()}

    def reset_bg_dir(self):
        self.cfg["bg_dir"] = ""
        self.save_config()
        return {"ok": True, "msg": "已恢复内置背景", "images": self.bg_images()}

    # ── 历史 ────────────────────────────────────────────────
    def clear_history(self):
        self.history = []
        return {"ok": True}

    def open_output(self):
        try:
            os.startfile(OUTPUT_DIR)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def open_in_explorer(self, path):
        try:
            subprocess.Popen(["explorer", "/select,", path])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def close(self):
        self.stop_monitor()
        proc = self.proc
        self.proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
                self.kill_tree(proc.pid)
            # 光 terminate 收不干净：uvicorn 有时候赖着不走，端口还听着，
            # 下次开程序又变成「复用外部服务」，进度条就没法用了
            for _ in range(24):
                if not self.port_open():
                    return
                time.sleep(0.25)
            self.kill_tree(proc.pid)
            for _ in range(24):
                if not self.port_open():
                    return
                time.sleep(0.25)
