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
