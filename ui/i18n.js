/* 界面文案的翻译表。
 *
 * 加一门语言只需要往 I18N 里加一份同结构的对象，再到 I18N_LANGS 注册名字。
 * 漏翻的键会退回中文并在控制台报警，不会把 key 直接印到界面上。
 */
const I18N_LANGS = {
  zh: "简体中文",
  en: "English",
};

const I18N = {
  zh: {
    // 顶栏
    "sub":            "GPT-SoVITS 权重推理",
    "btn.bg":         "背景图",
    "tip.bg":         "左键选文件夹，右键恢复内置",
    "btn.export":     "导出配置",
    "btn.import":     "导入配置",
    "btn.check":      "自检",
    "status.stopped": "服务未启动",

    // 目录栏
    "lbl.gsv":        "GPT-SoVITS 目录",
    "ph.gsv":         "选择 GPT-SoVITS 便携包目录",
    "btn.browse":     "浏览",
    "btn.auto":       "自动探测",
    "btn.start":      "启动服务",
    "btn.stop":       "停止",

    // 模型权重
    "card.model":     "模型权重",
    "hint.model":     "扫描 GPT_weights* / SoVITS_weights*",
    "btn.refresh":    "刷新列表",
    "btn.apply":      "应用模型",
    "btn.presets":    "已存组合…",
    "model.none":     "当前：未应用",

    // 参考音频
    "card.ref":       "参考音频",
    "hint.ref":       "音色由权重定，语气由它定",
    "btn.preview":    "试听",
    "btn.pick":       "浏览…",
    "lbl.prompt":     "参考文本（须与音频逐字一致）",
    "lbl.plang":      "参考语言",
    "btn.applyref":   "应用参考",
    "btn.bind":       "绑定到当前模型",
    "ref.unbound":    "参考：未绑定（换模型不会自动换参考）",

    // 系统资源
    "card.mon":       "系统资源",
    "lbl.device":     "推理设备",

    // 合成
    "card.synth":     "合成",
    "lbl.text":       "要念的文本",
    "lbl.tlang":      "文本语言",
    "params":         "推理参数",
    "chk.rand":       "每次随机 seed",
    "lbl.split":      "分句",
    "btn.synth":      "合成",
    "btn.play":       "试听",
    "btn.saveas":     "另存为…",
    "btn.openout":    "打开输出目录",
    "btn.batchedit":  "编辑台词",
    "btn.batchrun":   "批量替换素材",

    // 底部
    "card.hist":      "生成历史",
    "hint.hist":      "双击试听，右键定位",
    "th.time":        "时间",
    "th.text":        "文本",
    "th.dur":         "时长",
    "th.file":        "文件",
    "card.log":       "日志",
    "chk.fx":         "特效",

    // 弹层
    "modal.title":    "提示",
    "btn.cancel":     "取消",
    "btn.ok":         "知道了",

    // 状态与自检
    "status.ready":   "服务就绪",
    "status.starting": "启动中…",
    "check.title":    "自检",
    "device.cuda":    "独立显卡",
    "device.cpu":     "处理器",
  },

    "耗时": "耗时",

  en: {
    // top bar
    "sub":            "GPT-SoVITS inference",
    "btn.bg":         "Background",
    "tip.bg":         "Click to pick a folder, right-click to reset",
    "btn.export":     "Export config",
    "btn.import":     "Import config",
    "btn.check":      "Self-check",
    "status.stopped": "Service stopped",

    // folder bar
    "lbl.gsv":        "GPT-SoVITS folder",
    "ph.gsv":         "Pick the GPT-SoVITS portable folder",
    "btn.browse":     "Browse",
    "btn.auto":       "Auto-detect",
    "btn.start":      "Start service",
    "btn.stop":       "Stop",

    // model weights
    "card.model":     "Model weights",
    "hint.model":     "Scans GPT_weights* / SoVITS_weights*",
    "btn.refresh":    "Refresh",
    "btn.apply":      "Apply model",
    "btn.presets":    "Saved pairs…",
    "model.none":     "Current: not applied",

    // reference audio
    "card.ref":       "Reference audio",
    "hint.ref":       "Timbre comes from the weights, delivery from this clip",
    "btn.preview":    "Preview",
    "btn.pick":       "Browse…",
    "lbl.prompt":     "Reference text (must match the audio word for word)",
    "lbl.plang":      "Reference language",
    "btn.applyref":   "Apply reference",
    "btn.bind":       "Bind to model",
    "ref.unbound":    "Reference: unbound (switching models won't swap it)",

    // system
    "card.mon":       "System",
    "lbl.device":     "Inference device",

    // synthesize
    "card.synth":     "Synthesize",
    "lbl.text":       "Text to speak",
    "lbl.tlang":      "Text language",
    "params":         "Inference parameters",
    "chk.rand":       "Random seed each time",
    "lbl.split":      "Sentence split",
    "btn.synth":      "Synthesize",
    "btn.play":       "Preview",
    "btn.saveas":     "Save as…",
    "btn.openout":    "Open output folder",
    "btn.batchedit":  "Edit lines",
    "btn.batchrun":   "Batch replace",

    // bottom
    "card.hist":      "History",
    "hint.hist":      "Double-click to play, right-click to locate",
    "th.time":        "Time",
    "th.text":        "Text",
    "th.dur":         "Length",
    "th.file":        "File",
    "card.log":       "Log",
    "chk.fx":         "Effects",

    // modal
    "modal.title":    "Notice",
    "btn.cancel":     "Cancel",
    "btn.ok":         "Got it",

    // status & self-check
    "status.ready":   "Service ready",
    "status.starting": "Starting…",
    "check.title":    "Self-check",
    "device.cuda":    "GPU",
    "device.cpu":     "CPU",

    // —— 以下是动态文案，直接用中文原文当 key ——
    "提示": "Notice",
    "知道了": "Got it",
    "取消": "Cancel",
    "保存": "Save",
    "导入": "Import",

    "日语": "Japanese",
    "中文": "Chinese",
    "英语": "English",
    "韩语": "Korean",
    "粤语": "Cantonese",
    "自动": "Auto",
    "显卡 GPU": "GPU",
    "处理器 CPU": "CPU",
    "处理器": "CPU",
    "显卡": "GPU",

    "（没找到参考音频，点「浏览…」选一个）": "(no reference audio — click Browse…)",
    "（没扫到权重）": "(no weights found)",
    "读取中…": "Reading…",
    "未检测到独立显卡": "No discrete GPU detected",
    "已识别独显": "Discrete GPU detected",
    "无独显，只能 CPU": "No discrete GPU — CPU only",
    "目录不对": "Wrong folder",
    "没找到": "Not found",
    "常见位置都没找到 GPT-SoVITS 便携包，请手动点「浏览」选目录。":
      "No GPT-SoVITS portable package found in the usual places. Click Browse to pick the folder.",
    "找到多个": "Several found",
    "端口上已经有服务": "Port already in use",
    "接管并重启": "Take over and restart",
    "接管服务": "Take over",
    "先共用着": "Share it",
    "应用模型": "Apply model",
    "已存组合": "Saved pairs",
    "应用参考": "Apply reference",
    "合成": "Synthesize",
    "另存为": "Save as",
    "自检": "Self-check",
    "导出配置": "Export config",
    "导入配置": "Import config",
    "批量替换": "Batch replace",
    "没开始": "Not started",
    "编辑批量台词": "Edit batch lines",
    "切换设备": "Switch device",
    "无参考": "No reference",
    "服务未启动": "Service stopped",
    "参考：已绑定到当前模型": "Reference: bound to this model",
    "参考：未绑定（换模型不会自动换参考）":
      "Reference: unbound (switching models won't swap it)",
    "(空)": "(empty)",

    // 自检项名称与说明
    "GPT-SoVITS 目录": "GPT-SoVITS folder",
    "requests 模块": "requests module",
    "输出目录": "Output folder",
    "日志目录": "Log folder",
    "GPT 权重": "GPT weights",
    "SoVITS 权重": "SoVITS weights",
    "参考音频": "Reference audio",
    "Python 版本": "Python version",
    "运行推理子进程用": "runs the inference subprocess",
    "HTTP 请求": "HTTP requests",
    "空闲": "free",
    "被占用": "in use",
    "未设置": "not set",
    "打包运行，不适用": "bundled build — not applicable",
    "导出 mp3 用，缺了不影响合成": "mp3 export only; synthesis works without it",

    // 弹窗与提示
    "换成这条再试": "Use this one instead",
    "先算了": "Never mind",
    "套用": "Apply",
    "还没有绑定过组合。": "No saved pairs yet.",
    "在左边选好模型和参考音频，点「绑定到当前模型」，这里就会出现一条。":
      "Pick a model and a reference clip on the left, then click Bind to model — it will appear here.",
    "换机器或换目录时，绑定的文件找不到会自动隐藏，不会留一条点不动的废记录。":
      "On another machine or after moving folders, entries whose files are gone are hidden automatically.",
    "把下面这段复制走，换机器时用「导入配置」贴回来。":
      "Copy the text below; paste it back through Import config on the other machine.",
    "把之前导出的那段配置贴进来：": "Paste the config you exported earlier:",
    "每行一条：文件名|台词。留空则不生成该条。":
      "One per line: filename|line. Empty lines are skipped.",
    "通用音频（没有专属样本时，任意干净人声都能顶替）":
      "Generic clips (any clean voice works when the model has no samples)",
    "端口 {port} 上已经有一个 GPT-SoVITS 服务{pid}，它不是这个界面启动的。":
      "Port {port} already runs a GPT-SoVITS service{pid}, and it was not started by this window.",
    "共用它照样能合成，但加载模型和合成的进度都读不到，进度条只能按字数估算。":
      "Sharing it still synthesizes, but progress cannot be read — the bar falls back to a character estimate.",
    "接管会先把这个进程关掉，再用这里的运行环境重新启动一份，进度就准了，代价是模型要重新加载一次。":
      "Taking over closes that process and restarts one from here: progress becomes accurate, at the cost of reloading the model.",
    "耗时": "took",

  },
};

let I18N_CUR = "zh";

/** 取一条文案。vars 里的 {name} 会被替换。
 *
 * 两种用法并存：
 *   t("btn.synth")     静态界面用语义 key（index.html 的 data-i18n 走这条）
 *   t("合成")          动态文案直接拿中文原文当 key，省得再起一遍名字
 * 查不到时一律回退原文，并在控制台点名，方便加语言时查漏。
 */
function t(key, vars) {
  const table = I18N[I18N_CUR] || {};
  let s = table[key];

  if (s === undefined) {
    if (I18N_CUR === "zh") {
      s = key;                       // 中文模式：原文就是结果
    } else if (I18N.zh && I18N.zh[key] !== undefined) {
      s = I18N.zh[key];              // 语义 key 有中文对照
    } else {
      console.warn("[i18n] 缺翻译:", I18N_CUR, key);
      s = key;                       // 回退原文，绝不把 key 印到界面上
    }
  }

  if (vars) {
    for (const k in vars) {
      s = s.split("{" + k + "}").join(String(vars[k]));
    }
  }
  return s;
}

/** 把带 data-i18n* 的节点全部刷成当前语言。 */
function applyI18n() {
  document.documentElement.lang = I18N_CUR === "zh" ? "zh-CN" : I18N_CUR;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-ph"));
  });
  // 动态生成的内容（历史表、日志、自检结果）由调用方重新渲染
  if (typeof renderAllForLang === "function") {
    renderAllForLang();
  }
}

/** 切到某门语言。只改状态，落盘交给调用方。 */
function setLang(code) {
  I18N_CUR = I18N[code] ? code : "zh";
  applyI18n();
  const sel = document.getElementById("langSel");
  if (sel) sel.value = I18N_CUR;
}

// 后端和前端拼出来的消息走这里翻。界面文字已经由 t() 管了，
// 但 engine 发过来的日志行、弹窗标题、以及 JS 里拼接的句子不是键值对，
// 只能用模式匹配逐个换掉。
const I18N_LINES = [
  // 后端返回的消息
  [/^只支持 http 或 https 地址$/, "Only http and https addresses are supported"],
  [/^打不开浏览器：(.+)$/, "Could not open the browser: $1"],
  [/^对话框打不开$/, "Could not open the dialog"],
  [/^素材目录已设置$/, "Assets folder set"],
  [/^音频 \(\*\.wav;\*\.mp3;\*\.flac\)$/, "Audio (*.wav;*.mp3;*.flac)"],
  [/^所有文件 \(\*\.\*\)$/, "All files (*.*)"],
  [/^参考音频已选$/, "Reference audio selected"],
  [/^还没有生成过音频$/, "No audio has been generated yet"],
  [/^找不到 ffmpeg\.exe$/, "ffmpeg.exe not found"],
  [/^已导出：(.+)$/, "Exported: $1"],
  [/^已保存$/, "Saved"],
  [/^保存失败：(.+)$/, "Could not save: $1"],
  [/^没找到 GPT-SoVITS 便携包，需要先准备环境$/,
   "No GPT-SoVITS package found, it needs to be set up first"],
  [/^自动找回权重和参考音频时出错：(.+)$/,
   "Something went wrong while looking for the weights and reference audio: $1"],
  [/^有 (\d+) 个文件换了位置，已经接上$/, "$1 files moved, now reconnected"],
  [/^配置里记的位置没有文件了，在别的目录找到同名的，(.*)$/s,
   "The paths saved in the config point at files that are gone. Same name found " +
   "elsewhere, so they were switched over:"],
  [/^有 (\d+) 项要先处理$/, "$1 items need attention first"],
  [/^自检发现的，不处理的话合成会失败：(.*)$/s,
   "Found by the self-check. Synthesis will fail until these are fixed:"],
  [/^点顶上的「自检」看完整清单。$/, "Run Self-check for the full list."],
  [/^VocalithLoader 已就绪$/, "VocalithLoader is ready"],
  [/^启动失败，详见 logs.crash\.log$/, "Failed to start, see logs/crash.log"],

  // 没有 GPT-SoVITS 时的引导
  [/^还差一个 GPT-SoVITS 才能开始$/, "One more piece before you can start"],
  [/^VocalithLoader 本身只是操作界面，真正干活的是另一个软件，叫 GPT-SoVITS。它不在这个程序里，需要你另外准备。$/,
   "VocalithLoader is only the interface. The actual work is done by another " +
   "program called GPT-SoVITS, which is not bundled here and has to be set up separately."],
  [/^<b>有多大<\/b>：官方整合包解压后大约 30 GB，其中推理必需的部分约 13 GB。请先确认磁盘够用。$/,
   "<b>How big</b>: the official package is about 30 GB unpacked, and roughly " +
   "13 GB of that is needed for inference. Check your free space first."],
  [/^<b>怎么装<\/b>：<br>$/, "<b>How to install</b>:<br>"],
  [/^1\. 点下面的「打开下载页面」，在页面里找最新的整合包下载<br>$/,
   "1. Click Open download page below and grab the latest package<br>"],
  [/^2\. 下载下来是一个压缩包，右键选「解压到当前文件夹」<br>$/,
   "2. The download is an archive. Right click it and choose Extract here<br>"],
  [/^3\. 解压完打开那个文件夹，应该能直接看到 <b>runtime<\/b> 文件夹和 <b>api_v2\.py<\/b> 文件<br>$/,
   "3. Open the extracted folder. You should see a <b>runtime</b> folder and an " +
   "<b>api_v2.py</b> file<br>"],
  [/^4\. 回到这里点「选目录」，选那个文件夹$/, "4. Come back here, click Choose folder and pick it"],
  [/^已经有的话，直接点「选目录」。$/, "If you already have it, just click Choose folder."],
  [/^打开下载页面$/, "Open download page"],
  [/^选目录$/, "Choose folder"],

  // 前端拼接的日志与提示
  [/^\[参考\] 训练样本 (\d+) 条，另有通用音频 (\d+) 条$/,
   "[ref] $1 training samples, plus $2 generic voice clips"],
  [/^\[参考\] 训练样本 (\d+) 条$/, "[ref] $1 training samples"],
  [/^\[参考\] 当前模型是 (.+?)，自动用了它的训练样本当参考$/,
   "[ref] Current model is $1, so one of its training samples was picked as the reference"],
  [/^\[参考\] (.+?) 的训练样本，参考文本已跟着填好$/,
   "[ref] Training sample of $1, the reference text was filled in to match"],
  [/^\[参考\] 已切换参考音频$/, "[ref] Reference audio switched"],
  [/^\[参考\] 跟着模型换成 (.+?) 的训练样本$/,
   "[ref] Switched to a training sample of $1 along with the model"],
  [/^\[参考\] 切到 (.+)$/, "[ref] Switched to $1"],
  [/^\[参考\] 试听当前参考音频$/, "[ref] Previewing the current reference audio"],
  [/^\[批量\] 台词已保存，共 (\d+) 条$/, "[batch] Lines saved, $1 in total"],
  [/^\[启动\] 后端还没就绪：(.+)$/, "[start] Backend is not ready yet: $1"],
  [/^\[播放\] 浏览器拒绝播放：(.+)$/, "[play] The browser refused to play it: $1"],
  [/^\[i18n\] 语言下拉初始化失败$/, "[i18n] Could not set up the language selector"],
  [/^\[背景\] (.+)$/, "[background] $1"],
  [/^\[组合\] (.+)$/, "[set] $1"],

  // 角色名。后端在英文模式下已经换过，这里兜住仍带中文的旧数据
  [/企业 ?2/g, "Enterprise 2"],
  [/企业/g, "Enterprise"],
  [/海伦娜/g, "Helena"],
  [/雪风/g, "Yukikaze"],
];

// 把一段可能含中文的消息换成英文。翻不出来就原样返回。
function tl(text) {
  if (!text || typeof text !== "string" || I18N_CUR !== "en") return text;
  let out = text;
  for (const [pat, repl] of I18N_LINES) {
    if (pat.test(out)) out = out.replace(pat, repl);
  }
  return out;
}
