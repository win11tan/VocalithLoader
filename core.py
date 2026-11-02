# -*- coding: utf-8 -*-
"""
VocalithLoader — 后端核心（无界面依赖）

从 v1 的 voice_studio.py 搬过来的纯函数部分，逻辑一行没改：
日志进度解析、频谱计算、设备读写、便携包探测原本就是独立的，直接复用。
界面换成 pywebview 之后，改的只是外壳，这一层不动。
"""



import ctypes
import array
import json
import math
import os
import queue
import re
import socket
import string
import subprocess
import sys
import threading
import time
import unicodedata
import wave

from collections import deque

try:
    import requests
    REQUESTS_IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover
    # 以前这里静默降级成 None，结果要等到合成跑到最后一步才报
    # "'NoneType' object has no attribute 'post'"，完全看不出真正原因。
    # 把原始异常留下来，用的时候一起报出去
    requests = None
    REQUESTS_IMPORT_ERROR = _e

try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None

APP_TITLE = "VocalithLoader"
APP_VERSION = "1.0.3"

# 服务端每合完一句就会打这行，用来数真实进度
PROGRESS_MARK = "前端处理后的文本"
# 服务端每加载一项权重会打一行 Loading ... weights
LOAD_MARK = "Loading "
# 配置块里这四项就是需要加载的权重，分母从日志里实际数出来，不是写死的
LOAD_KEYS = ("t2s_weights_path", "vits_weights_path",
             "bert_base_path", "cnhuhbert_base_path")
LOAD_STEPS = 4          # 兜底值，只在日志里数不到配置时才用
LOAD_NAME_RE = re.compile(r"Loading (\w+) weights")
# 匹配配置行首的键。不能直接按子串判断，bert_base_path 是 cnhuhbert_base_path 的一部分
LOAD_KEY_RE = re.compile(r"(?m)^\s*(%s)\s*:" % "|".join(LOAD_KEYS))
LOAD_NAMES = {
    "Text2Semantic": "语义模型",
    "VITS": "声码器",
    "BERT": "文本特征",
    "CNHuBERT": "语音特征",
}
# tqdm 进度行里的百分比，例如 " 45%|████     | 675/1500 [00:05<00:06, 120it/s]"
TQDM_RE = re.compile(r"(\d+)%\|")

if getattr(sys, "frozen", False):
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(HERE, "config.json")
OUTPUT_DIR = os.path.join(HERE, "output")
LOG_DIR = os.path.join(HERE, "logs")

LANGS = ["ja", "zh", "en", "ko", "yue", "auto"]
SPLITS = ["cut0", "cut1", "cut2", "cut3", "cut4", "cut5"]
DEVICE_LABELS = ["自动", "显卡 GPU", "处理器 CPU"]
DEVICE_VALUES = {"自动": "auto", "显卡 GPU": "cuda", "处理器 CPU": "cpu"}

DEFAULT_BATCH_LINES = [
    ["line-1", ""],
    ["line-2", ""],
    ["line-3", ""],
    ["line-4", ""],
    ["line-5", ""],
    ["line-6", ""],
]

DEFAULT_CONFIG = {
    "gsv_dir": "",
    "host": "127.0.0.1",
    "port": 9880,
    # 界面语言。和 prompt_lang / text_lang 那些不是一回事：那些决定合成出来
    # 是什么语言，这个只决定按钮和标签上的字
    "ui_lang": "zh",
    "gpt_path": "",
    "sovits_path": "",
    "ref_audio": "",
    "prompt_text": "",
    "prompt_lang": "ja",
    "text_lang": "ja",
    "text": "",
    "top_k": 15,
    "top_p": 1.0,
    "temperature": 1.0,
    "repetition_penalty": 1.35,
    "text_split_method": "cut0",
    "seed": 42,
    "random_seed": False,
    "assets_dir": "",
    "profiles": {},
    "batch_lines": DEFAULT_BATCH_LINES,
    "fx": True,
    "device": "auto",
}

BG = "#0d1117"
BG2 = "#141b24"
BG3 = "#1b2430"
FG = "#e8f1ff"
FG_DIM = "#8fa8cc"
ACCENT = "#39ffd1"
ACCENT2 = "#3a7bff"
ERR = "#ff6b6b"

# 霓虹配色：都在 ACCENT 这同一支青绿上取值，明暗分档，避免配色花掉
NEON = ACCENT
NEON_MID = "#26b8a0"
NEON_DIM = "#17544c"
NEON_DEEP = "#0d2b27"
NEON_EDGE = "#1a5850"
WARN = "#ffc857"


def mix(c1, c2, t):
    """按 t（0 到 1）在两种 #rrggbb 之间插值。"""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def glow(c, t=0.35):
    """把颜色朝白色提一点，做出发光的感觉。"""
    return mix(c, "#ffffff", t)


def read_peaks(path, buckets=96):
    """把 wav 拆成若干段，每段取一个峰值，返回 0 到 1 的列表。

    画波形用峰值而不是 RMS：峰值出来的形状更接近人们熟悉的音频软件，
    而且说话的停顿一眼就能看出来。
    """
    try:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            sw = w.getsampwidth()
            n = w.getnframes()
            raw = w.readframes(n)
    except Exception:
        return []
    if not raw or n <= 0:
        return []
    try:
        if sw == 2:
            a = array.array("h")
            a.frombytes(raw[:len(raw) - len(raw) % 2])
            div = 32768.0
        elif sw == 1:
            a = array.array("B")
            a.frombytes(raw)
            div = 128.0
        elif sw == 4:
            a = array.array("i")
            a.frombytes(raw[:len(raw) - len(raw) % 4])
            div = 2147483648.0
        else:
            return []
    except Exception:
        return []
    if nch > 1:
        a = a[::nch]
    total = len(a)
    if total <= 0:
        return []
    step = max(1, total // buckets)
    peaks = []
    for b in range(buckets):
        s = b * step
        if s >= total:
            peaks.append(0.0)
            continue
        seg = a[s:s + step]
        peaks.append(min(1.0, max(max(seg), -min(seg)) / div))
    # 整体偏轻时拉满，否则轻声录音画出来几乎是一条平线
    top = max(peaks) or 0.0
    if 0.0 < top < 0.96:
        peaks = [min(1.0, p / top) for p in peaks]
    return peaks


def compute_spectrum(path, bands=32, hop=0.04, win=1024):
    """把音频算成短时频谱，返回 (每帧各频带的能量, 每秒帧数)。

    一次性把整段算完存成表，播放时只是按时间查表，不做实时 FFT，
    这样播放中完全不占 CPU，也不会掉帧。

    频带按对数切，因为等宽切线的话低频几个 bin 就吃掉大半宽度，
    出来的图会一直是左边几根巨柱、右边全趴着。
    """
    try:
        import numpy as np
    except Exception:
        return None, 0.0
    try:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            sw = w.getsampwidth()
            n = w.getnframes()
            rate = w.getframerate()
            raw = w.readframes(n)
    except Exception:
        return None, 0.0
    if not raw or rate <= 0:
        return None, 0.0
    try:
        if sw == 1:
            a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
        elif sw == 2:
            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        elif sw == 4:
            a = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        else:
            return None, 0.0
    except Exception:
        return None, 0.0
    if nch > 1:
        a = a[::nch]
    total = int(a.size)
    if total <= 0:
        return None, 0.0
    hop_n = max(1, int(rate * hop))
    frames = max(1, (total - win) // hop_n + 1) if total > win else 1
    need = (frames - 1) * hop_n + win
    if total < need:
        a = np.pad(a, (0, need - total))
        total = need
    nfft = 1 << int(math.ceil(math.log2(max(2, win))))
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    lo = 60.0
    hi = max(lo * 2.0, min(rate / 2.0, 8000.0))
    edges = np.logspace(math.log10(lo), math.log10(hi), bands + 1)
    spans = []
    last = 1
    for b in range(bands):
        i0 = int(np.searchsorted(freqs, edges[b]))
        i1 = int(np.searchsorted(freqs, edges[b + 1]))
        i0 = max(last, min(i0, len(freqs) - 1))
        i1 = max(i0 + 1, min(i1, len(freqs)))
        spans.append((i0, i1))
        last = i0 + 1
    window = np.hanning(win).astype(np.float32)
    idx = np.arange(frames)[:, None] * hop_n + np.arange(win)[None, :]
    mat = a[idx] * window
    spec = np.abs(np.fft.rfft(mat, nfft, axis=1))
    out = np.zeros((frames, bands), dtype=np.float32)
    for b, (i0, i1) in enumerate(spans):
        out[:, b] = spec[:, i0:i1].mean(axis=1)
    # 转 dB 再压到 0..1。线性能量的话，轻声段整条都是塌的
    db = 20.0 * np.log10(out + 1e-6)
    top = float(np.percentile(db, 99.0))
    floor = top - 55.0
    # top 极低说明整段几乎没有信号（静音文件、空录音）。不拦这一条的话，
    # 归一化会把一条平线拉成满格，界面上显示得像有声音
    if top - floor < 1.0 or top < -100.0:
        return None, 0.0
    base = np.clip((db - floor) / (top - floor), 0.0, 1.0)
    # 再按频带各自动态范围拉一次：人声的低频和高频天生比中频弱一大截，
    # 只做全局归一化的话这两头的柱子永远是趴着的，看着像坏了。
    level = np.zeros_like(base)
    for b in range(bands):
        col = db[:, b]
        hi = float(np.percentile(col, 96.0))
        lo = hi - 42.0
        if hi - lo < 5.0:
            continue
        g = np.clip((col - lo) / (hi - lo), 0.0, 1.0)
        # 该频带整体越弱，压得越低，免得把底噪也拉成满柱
        rel = float(np.mean(base[:, b]))
        weight = min(1.0, 0.38 + rel * 1.25)
        level[:, b] = g * weight
    return level.tolist(), 1.0 / hop


def count_marks(log_path, offset, mark):
    """数日志新增部分里 mark 出现了几次。

    尾部可能把一个标记切成两半，留几个字节到下次再读，宁可晚一拍也不漏数。
    """
    try:
        size = os.path.getsize(log_path)
    except Exception:
        return offset, 0
    if size <= offset:
        return offset, 0
    try:
        with open(log_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset)
    except Exception:
        return offset, 0
    if not chunk:
        return offset, 0
    text = chunk.decode("utf-8", "ignore")
    count = text.count(mark)
    if not count:
        # 万一服务是别的方式启动的，日志可能按系统 ANSI 写出来，再试一次
        count = chunk.decode("gbk", "ignore").count(mark)
    back = min(len(mark.encode("utf-8")) - 1, len(chunk))
    return offset + len(chunk) - back, count


def read_progress(log_path, offset):
    """数「完成一句」的标记，用来算合成进度。"""
    return count_marks(log_path, offset, PROGRESS_MARK)


def read_load_steps(log_path, offset):
    """数「加载了一项权重」的标记，用来算加载模型阶段的进度。"""
    return count_marks(log_path, offset, LOAD_MARK)


def scan_load(log_path, offset):
    """读日志新增部分，同时数出加载项数和这一版实际要加载几项。

    分母不写死：服务端启动时会把完整配置打出来，里面有哪几个权重路径就说明
    要加载几项，不同版本、不同配置各不相同。数不到才退回经验值。

    返回 (新偏移, 新增项数, 配置里的项数, 最近加载的那项名字)。
    """
    try:
        size = os.path.getsize(log_path)
    except Exception:
        return offset, 0, 0, None
    if size <= offset:
        return offset, 0, 0, None
    try:
        with open(log_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset)
    except Exception:
        return offset, 0, 0, None
    if not chunk:
        return offset, 0, 0, None
    text = chunk.decode("utf-8", "ignore")
    steps = text.count(LOAD_MARK)
    conf = len(set(LOAD_KEY_RE.findall(text)))
    names = LOAD_NAME_RE.findall(text)
    back = min(240, len(chunk))
    return offset + len(chunk) - back, steps, conf, (names[-1] if names else None)


def count_sentences(text):
    """粗略数一下这段文本会被切成几句，用来当进度条的分母。

    服务端实际怎么切只有它自己知道，这里按标点估个大概就够了：
    少了会被截在 99%，多了最后强制补满，都不影响可用。
    """
    parts = re.split(r"[。．！？!?…；;]+|[\r\n]+", text or "")
    return max(1, sum(1 for p in parts if p.strip()))


def read_tqdm(log_path, offset):
    """从 stderr 日志里取最近一次 tqdm 的百分比。

    服务端每合一句都会跑一个 0 到 1500 的 tqdm，那是这句的 token 进度。
    有了它，进度条在两句之间也能一直往前爬，而不是跳一格停一秒。
    """
    try:
        size = os.path.getsize(log_path)
    except Exception:
        return offset, None
    if size <= offset:
        return offset, None
    try:
        with open(log_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset)
    except Exception:
        return offset, None
    if not chunk:
        return offset, None
    text = chunk.decode("utf-8", "ignore")
    hits = TQDM_RE.findall(text)
    frac = int(hits[-1]) / 100.0 if hits else None
    # 一行 tqdm 挺长，多留点尾巴防止被截成两段解析失败
    back = min(240, len(chunk))
    return offset + len(chunk) - back, frac


def short_name(s):
    """把 CPU / GPU 的官方名称压短，去掉商标符号和频率尾巴。

    注册表里给的是 Intel(R) Core(TM) Ultra 9 275HX，太长了塞不进状态行。
    """
    if not s:
        return ""
    s = s.replace("(R)", "").replace("(TM)", "").replace("(r)", "").replace("(tm)", "")
    s = re.sub(r"\s+CPU\s+@.*$", "", s, flags=re.I)
    s = re.sub(r"\s+GPU\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+Processor\s*$", "", s, flags=re.I)
    # 去掉厂商前缀，保留 Core / GeForce 这类系列名，用户更好认
    for p in ("Intel ", "AMD ", "NVIDIA ", "Genuine "):
        if s.startswith(p):
            s = s[len(p):]
            break
    return re.sub(r"\s+", " ", s).strip()


def cpu_name():
    """读注册表拿处理器型号。

    platform.processor() 只会给 Intel64 Family 6 Model 158 这种，
    对人来说等于没说，还是注册表里的名字直观。
    """
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return short_name(val or "")
    except Exception:
        return ""


def gpu_available():
    """这台机器有没有能用的 NVIDIA 显卡。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=8)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def yaml_path_of(gsv_dir):
    return os.path.join(gsv_dir, "GPT_SoVITS", "configs", "tts_infer.yaml")


def read_device(gsv_dir):
    """读当前用的推理设备，返回 cuda 或 cpu。"""
    try:
        with open(yaml_path_of(gsv_dir), "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return "cuda"
    head = text.split("\nv1:")[0]
    m = re.search(r"(?m)^\s+device:\s*(\S+)", head)
    return m.group(1).strip() if m else "cuda"


def write_device(gsv_dir, device):
    """把推理设备写进 tts_infer.yaml 的 custom 段，改之前先备份。

    只动 device 和 is_half 两行，别的原样保留。CPU 下 is_half 必须关掉，
    否则半精度运算在没有显卡的机器上会直接报错。
    """
    path = yaml_path_of(gsv_dir)
    if not os.path.isfile(path):
        return False, "找不到 tts_infer.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return False, "读取失败: %s" % e
    marker = "\nv1:"
    if marker in text:
        head, tail = text.split(marker, 1)
        tail = marker + tail
    else:
        head, tail = text, ""
    half = "true" if device == "cuda" else "false"
    new_head = re.sub(r"(?m)^(\s+device:\s*)\S+", r"\g<1>" + device, head)
    new_head = re.sub(r"(?m)^(\s+is_half:\s*)\S+", r"\g<1>" + half, new_head)
    if new_head == head:
        return False, "配置里没有找到 device 字段"
    try:
        if not os.path.isfile(path + ".bak"):
            with open(path + ".bak", "w", encoding="utf-8") as f:
                f.write(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_head + tail)
    except Exception as e:
        return False, "写入失败: %s" % e
    return True, ""


def is_gsv_dir(path):
    """判断一个目录是不是可用的 GPT-SoVITS 运行时。"""
    if not path or not os.path.isdir(path):
        return False
    py = os.path.join(path, "runtime", "python.exe")
    api = os.path.join(path, "api_v2.py")
    return os.path.isfile(py) and os.path.isfile(api)


SKIP_DIRS = {
    "windows", "programdata", "appdata", "$recycle.bin", "system volume information",
    "node_modules", ".git", ".cache", "temp", "tmp", "windows.old", "recovery",
    "perflogs", "msocache", "config.msi", "intel", "amd", "nvidia",
}


def looks_like_gsv_name(name):
    n = name.lower()
    return ("sovits" in n) or n.startswith("gpt-sovits") or ("gpt-sovits" in n)


def detect_gsv(time_budget=8.0, log=None):
    """在常见位置找 GPT-SoVITS 便携包。

    先看几个几乎不花时间的高概率位置（当前目录、下载、桌面），
    再扫各盘根目录及其下一层，这样「某个下载目录\\GPT-SoVITS-xxx」这种
    隔着两层的也能找到。全程有时间预算，到点就返回已找到的结果。
    """
    t0 = time.time()
    found = []

    def note(msg):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    def add(path):
        if not path or path in found:
            return
        if is_gsv_dir(path):
            found.append(path)
            note("找到：%s" % path)

    home = os.path.expanduser("~")

    # 一、高概率位置，直接看下一层
    quick_roots = [HERE, os.path.dirname(HERE), home,
                   os.path.join(home, "Downloads"), os.path.join(home, "下载"),
                   os.path.join(home, "Desktop"), os.path.join(home, "桌面")]
    for base in quick_roots:
        if not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                if looks_like_gsv_name(name):
                    add(os.path.join(base, name))
        except Exception:
            continue

    # 二、各盘根的根目录：先看自己，再看下一层。
    # 盘符从 A 到 Z 逐个试，存在的才扫，所以装在哪个盘都能找到，不写死列表。
    for letter in string.ascii_uppercase:
        drive = letter + ":\\"
        if not os.path.isdir(drive):
            continue
        try:
            entries = os.listdir(drive)
        except Exception:
            continue
        for name in entries:
            if time.time() - t0 > time_budget:
                note("扫描超时，先用手动选择也可以")
                return found
            low = name.lower()
            if low in SKIP_DIRS or name.startswith("$"):
                continue
            p = os.path.join(drive, name)
            if not os.path.isdir(p):
                continue
            if looks_like_gsv_name(name):
                add(p)
                continue
            # 第二层：<下载目录>\GPT-SoVITS-xxx
            try:
                for sub in os.listdir(p):
                    if time.time() - t0 > time_budget:
                        note("扫描超时，先用手动选择也可以")
                        return found
                    if looks_like_gsv_name(sub):
                        add(os.path.join(p, sub))
            except Exception:
                continue
    return found


WEIGHT_EXTS = (".ckpt", ".pth")
AUDIO_EXTS = (".wav", ".mp3", ".flac")


def drive_roots():
    """列出实际存在的盘符根目录，A 到 Z 逐个试，不写死。"""
    out = []
    for letter in string.ascii_uppercase:
        d = letter + ":\\"
        try:
            if os.path.isdir(d):
                out.append(d)
        except OSError:
            continue
    return out


def role_from_name(filename):
    """从权重或样本文件名里取角色名。

    helena-e12.ckpt      -> helena
    helena_e8_s464.pth   -> helena
    enterprise2-e8.ckpt  -> enterprise2
    """
    base = os.path.basename(filename or "")
    low = base.lower()
    for ext in WEIGHT_EXTS + AUDIO_EXTS:
        if low.endswith(ext):
            base = base[: -len(ext)]
            break
    for sep in ("-", "_", " "):
        if sep in base:
            head = base.split(sep)[0].strip()
            if head:
                return head.lower()
    return base.strip().lower()


def scan_files(roots, exts, name_filter=None, max_depth=5,
               time_budget=10.0, skip_dirs=None, log=None):
    """在若干根目录下找指定扩展名的文件。

    配置里的路径失效多半是因为目录被搬走了，文件其实还在盘上某处。
    全盘遍历代价太大，所以这里三道闸：限制深度、跳过系统目录、到点收工。
    返回 [{path, name, size, mtime, role}]，按修改时间从新到旧。

    name_filter 收一个已转小写的文件名，返回 True 才算命中。
    """
    exts = tuple(e.lower() for e in exts)
    skip = set(SKIP_DIRS if skip_dirs is None else skip_dirs)
    deadline = time.time() + max(0.1, float(time_budget))
    out = []
    seen = set()
    hit_limit = []

    def want(name):
        low = name.lower()
        if not low.endswith(exts):
            return False
        return True if name_filter is None else bool(name_filter(low))

    def walk(d, depth):
        if depth > max_depth or time.time() > deadline:
            if time.time() > deadline:
                hit_limit.append(1)
            return
        try:
            it = os.scandir(d)
        except OSError:
            return
        with it:
            for entry in it:
                if time.time() > deadline:
                    hit_limit.append(1)
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        low = entry.name.lower()
                        if low in skip or entry.name.startswith("$"):
                            continue
                        walk(entry.path, depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        if not want(entry.name):
                            continue
                        full = os.path.abspath(entry.path)
                        if full in seen:
                            continue
                        seen.add(full)
                        try:
                            st = entry.stat()
                            size, mtime = st.st_size, st.st_mtime
                        except OSError:
                            size, mtime = 0, 0.0
                        out.append({
                            "path": full,
                            "name": entry.name,
                            "size": size,
                            "mtime": mtime,
                            "role": role_from_name(entry.name),
                        })
                except OSError:
                    continue

    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        walk(root, 0)
        if hit_limit:
            if log:
                try:
                    log("扫描到时间上限，先停下，已找到 %d 个" % len(out))
                except Exception:
                    pass
            break

    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def slice_wav_center(src, dst, seconds=5.0):
    """从一段音频中间截 seconds 秒，另存成 wav。

    训练集里的原始音频往往一两分钟，直接喂给 GPT-SoVITS 会被拒（只收 3 到
    10 秒），切中间那段最保险：开头结尾常有淡入淡出和静音。
    只处理 PCM wav，别的格式说明解不了，返回空串。
    """
    try:
        with wave.open(src, "rb") as r:
            ch, width, rate = r.getnchannels(), r.getsampwidth(), r.getframerate()
            total = r.getnframes()
            if not rate or total <= 0:
                return ""
            want = int(rate * float(seconds))
            if total <= want:
                start = 0
                want = total
            else:
                start = max(0, (total - want) // 2)
            r.setpos(start)
            frames = r.readframes(want)
    except Exception:
        return ""
    try:
        with wave.open(dst, "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(frames)
    except Exception:
        return ""
    return dst





_MSG_RULES = [
    # 顺序有讲究：更具体的规则放前面，否则会被宽泛的规则先吃掉
    (r"^扫描到 GPT (\d+) 个 / SoVITS (\d+) 个$",
     r"Scanned \1 GPT weights and \2 SoVITS weights"),
    (r"^自检：(\d+) 项需要处理（(.+)）$", r"Self-check: \1 items need attention (\2)"),
    (r"^自检完成，全部通过$", r"Self-check passed"),
    (r"^VocalithLoader 已就绪$", r"VocalithLoader is ready"),
    (r"^建目录失败 (.+): (.+)$", r"Could not create the folder \1: \2"),
    (r"^配置文件读不出来，已退回默认设置：(.+)$",
     r"Config file could not be read, falling back to defaults: \1"),
    (r"^保存配置失败: (.+)$", r"Could not save the config: \1"),
    (r"^扫描模型失败: (.+)$", r"Could not scan for models: \1"),
    (r"^服务已在运行$", r"The service is already running"),
    (r"^注意：这台机器有显卡（(.+?)），但配置里写的是 CPU 推理。"
     r"把「推理设备」切到显卡大约快 3~4 倍$",
     r"This machine has a GPU (\1) but the config says CPU inference. "
     r"Switching the device to GPU is roughly three to four times faster"),
    (r"^端口 (.+?) 上已经有一个 GPT-SoVITS 服务（pid (.+?)），不是本程序启动的$",
     r"Port \1 already has a GPT-SoVITS service (pid \2) that this app did not start"),
    (r"^复用它读不到加载和合成的进度，条子只能按字数估；想要准确的进度就点「接管并重启」$",
     r"Reusing it hides the loading and synthesis progress, so the bars fall back to "
     r"estimating from character count. Use Take over and restart for accurate progress"),
    (r"^启动服务 pid=(\d+)，加载模型…$", r"Started the service, pid \1, loading weights"),
    (r"^硬件：(.+?) ｜ (.+)$", r"Hardware: \1 | \2"),
    (r"^接管服务：先结束端口 (\d+) 上的进程 pid=(\d+)$",
     r"Taking over: stopping the process on port \1 first, pid \2"),
    (r"^端口空出来了，用本程序的运行环境重新启动$",
     r"Port is free now, restarting with this app's own runtime"),
    (r"^服务退出，见 logs/api_err\.log$", r"Service exited, see logs/api_err.log"),
    (r"^加载超时，见 logs/api_err\.log$", r"Loading timed out, see logs/api_err.log"),
    (r"^服务就绪：(.+?)（本次加载权重 (\d+) 项）$",
     r"Service ready at \1, \2 weight files loaded this time"),
    (r"^正在停止服务 pid=(\d+)…$", r"Stopping the service, pid \1"),
    (r"^端口 (.+?) 上的服务（pid (.+?)）不是本程序启动的，这边停不了它$",
     r"The service on port \1 (pid \2) was not started by this app, so it cannot be "
     r"stopped from here"),
    (r"^想彻底关掉就去它自己的窗口里按 Ctrl\+C；想让它变成这边能管、能看进度的，"
     r"点「启动服务」选接管$",
     r"To shut it down completely, press Ctrl+C in its own window. To make it "
     r"manageable with progress here, start the service and choose take over"),
    (r"^GPT → (.+?) \((\d+)\)$", r"GPT applied: \1 (\2)"),
    (r"^SoVITS → (.+?) \((\d+)\)$", r"SoVITS applied: \1 (\2)"),
    (r"^应用模型失败: (.+)$", r"Could not apply the weights: \1"),
    (r"^提醒：参考文本为空，音色可能不准，建议填上与音频一致的文字$",
     r"Heads up: the reference text is empty, so the timbre may be off. "
     r"Fill in the words actually spoken in the clip"),
    (r"^参考音频已应用 \((\d+)\)$", r"Reference audio applied (\1)"),
    (r"^应用参考失败: (.+)$", r"Could not apply the reference audio: \1"),
    (r"^已绑定：(.+)$", r"Bound to \1"),
    (r"^已套用组合：(.+)$", r"Applied the set \1"),
    (r"^参考音频还没选，先拿 (.+?) 顶上（五秒以上、干净人声就行）$",
     r"No reference audio selected yet, using \1 for now. "
     r"Any clean voice clip over five seconds will do"),
    (r"^这段 (\d+) 字，(.+?)上预计 (.+)$",
     r"\1 characters, about \3 on the \2"),
    (r"^已生成 (.+?)（(.+?)s / 耗时 (.+?)s）$", r"Wrote \1 (\2 s of audio in \3 s)"),
    (r"^合成失败: (.+)$", r"Synthesis failed: \1"),
    (r"^已完成 0/(\d+) 句$", r"0 of \1 lines done"),
    (r"^正在合成 (\d+) 句…（估算）$", r"Synthesising \1 lines (estimated)"),
    (r"^正在合成 (\d+) 句…估算 (\d+)%（已等待 (.+?) 秒，外部服务看不到细节）$",
     r"Synthesising \1 lines, about \2 percent (waited \3 s, "
     r"an external service hides the details)"),
    (r"^推理设备写为 (.+?)，下次启动服务生效$",
     r"Inference device set to \1, takes effect the next time the service starts"),
    (r"^配置已导入$", r"Config imported"),
    (r"^已导出：(.+)$", r"Exported: \1"),
    (r"^没找到 GPT-SoVITS 便携包，需要先准备环境$",
     r"No GPT-SoVITS package found, it needs to be set up first"),
    (r"^自动找回权重和参考音频时出错：(.+)$",
     r"Something went wrong while looking for the weights and reference audio: \1"),
    (r"^启动失败，详见 logs.crash\.log$", r"Failed to start, see logs/crash.log"),
    (r"^GPT-SoVITS 目录：(.+)$", r"GPT-SoVITS folder: \1"),
    (r"^已替换 (.+?)\.mp3$", r"Replaced \1.mp3"),
    (r"^替换 (.+?) 失败: (.+)$", r"Could not replace \1: \2"),
    (r"^批量完成 (\d+)/(\d+)，原件备份在 _bak_original$",
     r"Batch finished \1 of \2, originals backed up in _bak_original"),
    (r"^参考音频没了，从训练原始音频切了一段：(.+)$",
     r"Reference audio was gone, sliced a fresh clip from the training source: \1"),
    (r"^(.+?) 原来的位置没了，已改用：(.+)$",
     r"\1 is no longer where it was, switched to: \2"),
    # 状态条与进度条
    (r"^服务就绪（已有实例）$", r"Service ready (existing instance)"),
    (r"^服务就绪（外部实例）$", r"Service ready (external instance)"),
    (r"^服务就绪$", r"Service ready"),
    (r"^服务未启动$", r"Service not started"),
    (r"^服务已退出$", r"Service exited"),
    (r"^服务已停止$", r"Service stopped"),
    (r"^加载中…$", r"Loading"),
    (r"^加载超时$", r"Loading timed out"),
    (r"^正在停止…$", r"Stopping"),
    (r"^正在停止服务…$", r"Stopping the service"),
    (r"^正在应用模型…$", r"Applying weights"),
    (r"^模型已应用$", r"Weights applied"),
    (r"^模型应用失败$", r"Weights failed to apply"),
    (r"^模型加载完成$", r"Weights loaded"),
    (r"^合成中…$", r"Synthesising"),
    (r"^完成$", r"Done"),
    (r"^正在加载模型 0/(\d+)$", r"Loading weights 0 of \1"),
    (r"^正在加载模型 (\d+)/(\d+) · (.+?)（已等待 (.+?) 秒）$",
     r"Loading weights \1 of \2, \3 (waited \4 s)"),
    (r"^正在加载模型 (\d+)/(\d+)（已等待 (.+?) 秒）$",
     r"Loading weights \1 of \2 (waited \3 s)"),
    (r"^模型加载完毕，正在启动服务…（已等待 (.+?) 秒）$",
     r"Weights loaded, starting the service (waited \1 s)"),
    (r"^正在合成 (\d+) 句…（已等待 (.+?) 秒）$",
     r"Synthesising \1 lines (waited \2 s)"),
    # 合成进度：先是括号里的等待/预计，再拼整句
    (r"（已等待 (.+?) 秒\s*/\s*预计 (\d+) 分 (\d+) 秒）",
     r"(waited \1 s, about \2 min \3 s left)"),
    (r"（已等待 (.+?) 秒\s*/\s*预计 (\d+) 秒）",
     r"(waited \1 s, about \2 s left)"),
    (r"（已等待 (.+?) 秒）", r"(waited \1 s)"),
    (r"（已等待 (.+?) 秒 / 预计 (.+?)）", r"(waited \1 s, about \2 left)"),
    (r"^已完成 (\d+)/(\d+) 句 · 正在合成第 (\d+) 句(.*)$",
     r"\1 of \2 lines done, synthesising line \3 \4"),
    (r"^已完成 (\d+)/(\d+) 句(.*)$", r"\1 of \2 lines done \3"),
    (r"^正在切分文本、提取特征…(.*)$", r"Splitting text and extracting features... \1"),
    # 自检项的名称与说明
    (r"^GPT-SoVITS 目录$", r"GPT-SoVITS folder"),
    (r"^requests 模块$", r"requests module"),
    (r"^输出目录$", r"Output folder"),
    (r"^日志目录$", r"Log folder"),
    (r"^端口 (\d+)$", r"Port \1"),
    (r"^GPT 权重$", r"GPT weights"),
    (r"^SoVITS 权重$", r"SoVITS weights"),
    (r"^参考音频$", r"Reference audio"),
    (r"^Python 版本$", r"Python version"),
    (r"^运行推理子进程用$", r"launches the inference process"),
    (r"^HTTP 请求$", r"HTTP requests"),
    (r"^空闲$", r"free"),
    (r"^被占用$", r"in use"),
    (r"^未设置$", r"not set"),
    (r"^打包运行，不适用$", r"not applicable when packaged"),
    (r"^导出 mp3 用，缺了不影响合成$", r"only for mp3 export, synthesis works without it"),
    (r"^加载失败：(.+)$", r"failed to load: \1"),
    (r"^原因未知$", r"reason unknown"),
]

# 夹在长句里的碎片，整句规则够不着的地方用它。长的写在前面先换，
# 否则「未检测到独立显卡」会被「显卡」先拆开。
_MSG_PIECES = [
    ("未检测到独立显卡", "no discrete GPU detected"),
    ("SoVITS 权重", "SoVITS weights"),
    ("GPT 权重", "GPT weights"),
    ("参考音频", "Reference audio"),
    ("推理设备", "inference device"),
    ("独显", "a discrete card"),
    ("未知", "unknown"),
    ("显卡", "GPU"),
    ("处理器", "CPU"),
    ("秒左右", "seconds"),
    (" 分 ", " min "),
]

# 角色名的中英对照，日志和下拉框都要用
MODEL_NAME_EN = {
    "企业 2": "Enterprise 2",
    "企业2": "Enterprise 2",
    "企业": "Enterprise",
    "海伦娜": "Helena",
    "雪风": "Yukikaze",
}


def localize(text, lang="zh"):
    """把界面上的中文消息换成英文。

    只在英文模式下动手；匹配不上就原样返回，所以漏词不会崩，
    最多是那一条还留着中文，之后补规则即可。
    """
    if not text or lang != "en":
        return text
    before = str(text)
    out = before
    for pat, repl in _MSG_RULES:
        out = re.sub(pat, repl, out)
    if out != before:
        for zh, en in _MSG_PIECES:
            out = out.replace(zh, en)
    return out


def model_name(name, lang="zh"):
    """企业 -> Enterprise，其余原样。"""
    if not name:
        return name
    if lang != "en":
        return name
    return MODEL_NAME_EN.get(name.strip(), name)


def fmt_duration(path):
    try:
        with wave.open(path, 'rb') as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def safe_filename(text, limit=20):
    """把任意文本转成 Windows 允许的文件名片段。

    处理的情况：
    1. 文件名保留字符 \\ / : * ? " < > |
    2. 所有 Unicode 控制字符与格式字符（Cc/Cf/Cs），包括换行、制表符、
       零宽空格、方向控制符
    3. 行分隔符 Zl 与段分隔符 Zp（\u2028 \u2029，它们在文件名里同样非法）
    4. 首尾的点与空格（Windows 不允许文件名以点或空格结尾）
    5. 清理后只剩标点或符号时退回 clip，避免出现「。。。」这种文件名
    6. 超长截断，避免路径整体超过 260 字符
    """
    bad = set('\\/:*?"<>|')
    chars = []
    for ch in text:
        if ch in bad:
            continue
        cat = unicodedata.category(ch)
        if cat[0] == "C":  # Cc 控制、Cf 格式、Cs 代理、Co 私用、Cn 未分配
            continue
        if cat in ("Zl", "Zp"):
            continue
        chars.append(ch)
    out = "".join(chars).strip(" .")
    if not any(ch.isalnum() for ch in out):
        return "clip"
    return out[:limit]


def check_text(text):
    """合成前的文本体检，返回提示语（空字符串表示没问题）。"""
    t = (text or "").strip()
    if not t:
        return "文本为空"
    if len(t) > 3000:
        return "文本较长（%d 字），合成会明显变慢，建议分成几段" % len(t)
    # 只有标点或符号，念出来通常是空的
    if not any(ch.isalnum() for ch in t):
        return "文本里没有可发音的字，只有标点或符号"
    return ""


def unique_path(directory, stem, ext=".wav"):
    """同秒重复合成时避免互相覆盖。"""
    path = os.path.join(directory, stem + ext)
    i = 2
    while os.path.exists(path):
        path = os.path.join(directory, "%s_%d%s" % (stem, i, ext))
        i += 1
    return path


