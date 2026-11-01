/* VocalithLoader 前端
   和后端只通过两条线联系：
     window.pywebview.api.xxx()  调后端
     window.__push({kind,data})  收后端推来的事件
   其余全部在这里，界面状态自己维护，不来回问后端。 */

const LANGS = ["ja", "zh", "en", "ko", "yue", "auto"];
// 值还是那边的语言代码，只是界面上别再让人看 ja、zh 这种
const LANG_ZH = { ja: "日语", zh: "中文", en: "英语", ko: "韩语", yue: "粤语", auto: "自动" };
// 显示名要跟着界面语言变，所以每次现算，不能在加载时 map 死
const langPairs = () => LANGS.map((v) => [v, t(LANG_ZH[v] || v)]);
const SPLITS = ["cut0", "cut1", "cut2", "cut3", "cut4", "cut5"];
const DEVICES = ["自动", "显卡 GPU", "处理器 CPU"];
const $ = (id) => document.getElementById(id);
const api = () => window.pywebview.api;

const S = {
  cfg: {},
  models: { gpt: [], sovits: [] },
  modelMap: {},
  history: [],
  lastWav: "",
  wave: [],
  spec: null,
  playing: null,
  bg: { list: [], idx: 0, timer: null },
  ready: false,
  busy: false,
  dpr: window.devicePixelRatio || 1,
};

/* ── 工具 ─────────────────────────────────────────────── */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function baseName(p) {
  // 不用正则：JS 正则里的反斜杠经过几层转义很容易丢，直接按字符找分隔符最稳
  const s = String(p == null ? "" : p);
  const cut = Math.max(s.lastIndexOf("/"), s.lastIndexOf(String.fromCharCode(92)));
  return cut >= 0 ? s.slice(cut + 1) : s;
}

function modelKeyOf(gptPath) {
  const f = baseName(gptPath);
  return f.split(/[-_.]/)[0].toLowerCase();
}

function fileUrl(p) {
  return "file:///" + String(p).replace(/\\/g, "/").replace(/^\/+/, "");
}
function fitCanvas(cv) {
  const w = cv.clientWidth || 300;
  const h = cv.clientHeight || 60;
  if (cv.width !== Math.round(w * S.dpr) || cv.height !== Math.round(h * S.dpr)) {
    cv.width = Math.round(w * S.dpr);
    cv.height = Math.round(h * S.dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
  return { ctx: ctx, w: w, h: h };
}

function toastLike(text, ok) {
  // 轻提示挂在顶栏状态右边，不打断操作
  const el = $("status");
  el.classList.remove("ok", "busy", "err");
  el.classList.add(ok ? "ok" : "err");
  el.innerHTML = '<i class="dot"></i>' + esc(text);
}

/* ── 后端推来的事件 ───────────────────────────────────── */
window.__push = function (msg) {
  const d = msg.data || {};
  switch (msg.kind) {
    case "log":
      addLog(d.line);
      break;
    case "status":
      setStatus(d.text, d.ok ? "ok" : (d.busy ? "busy" : ""));
      break;
    case "progress":
      setProgress(d.value, d.text, d.mode);
      break;
    case "models":
      fillModels(d);
      break;
    case "monitor":
      paintMonitor(d);
      break;
    case "history":
      addHistory(d);
      break;
    case "toast":
      toastLike(d.text, d.kind !== "err");
      break;
    case "hint":
      modal(d.title || t("提示"), d.body || "");
      break;
    case "model_now":
      $("modelNow").textContent = d.text;
      $("modelNow").style.color = d.ok ? "var(--accent)" : "var(--err)";
      break;
    case "state":
      S.ready = !!d.ready;
      S.busy = !!d.busy;
      syncButtons();
      break;
    case "cfg":
      S.cfg = d;
      if (d.ui_lang && d.ui_lang !== I18N_CUR) setLang(d.ui_lang);
      fillControls();
      break;
  }
};

/* ── 状态行 / 按钮可用性 ──────────────────────────────── */
function setStatus(text, kind) {
  const el = $("status");
  el.className = "status" + (kind ? " " + kind : "");
  el.innerHTML = '<i class="dot"></i>' + esc(text || "");
}
function syncButtons() {
  $("btnStart").disabled = S.ready || S.busy;
  $("btnStop").disabled = !S.ready && !S.busy;
  $("btnSynth").disabled = !S.ready || S.busy;
  $("btnApplyModel").disabled = !S.ready;
  $("btnApplyRef").disabled = !S.ready;
}

/* 界面语言下拉。注意它和上面 LANGS 里那些语音语言不是一回事：
   那些决定合成出来是哪种语言，这个只换界面上的字。 */
function initLangSelect() {
  const sel = $("langSel");
  if (!sel || sel.options.length) return;
  sel.innerHTML = Object.keys(I18N_LANGS)
    .map((code) => '<option value="' + esc(code) + '">' + esc(I18N_LANGS[code]) + "</option>")
    .join("");
  sel.value = I18N_CUR;
  sel.onchange = async () => {
    setLang(sel.value);
    try {
      await api().update_cfg({ ui_lang: sel.value });
    } catch (e) { /* 存不下也不影响这次会话 */ }
  };
}

/* 切换语言后，静态文本已经由 applyI18n 刷完，这里补上动态生成的部分。
   刻意不碰输入框和文本框：用户可能正写到一半。 */
function renderAllForLang() {
  const pl = $("selPLang").value;
  const tl = $("selTLang").value;
  const dv = $("selDevice").value;
  fillSelectPairs($("selPLang"), langPairs());
  fillSelectPairs($("selTLang"), langPairs());
  fillSelect($("selDevice"), DEVICES, t);
  $("selPLang").value = pl;
  $("selTLang").value = tl;
  if (dv) $("selDevice").value = dv;
  renderHistory(S.history);
}

/* ── 日志 ─────────────────────────────────────────────── */
function addLog(line) {
  const box = $("logBox");
  const div = document.createElement("div");
  div.className = "new";
  div.textContent = line;
  box.appendChild(div);
  // 只留最后 800 行，长时间挂着也不至于越滚越慢
  while (box.childNodes.length > 800) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
  setTimeout(() => div.classList.remove("new"), 900);
}

/* ── 进度 ─────────────────────────────────────────────── */
function setProgress(value, text, mode) {
  const bar = $("progBar");
  if (mode === "indeterminate") {
    bar.style.width = "100%";
    bar.style.opacity = "0.45";
  } else {
    bar.style.opacity = "1";
    bar.style.width = Math.max(0, Math.min(100, (value || 0) * 100)) + "%";
  }
  if (text !== undefined) $("progText").textContent = text || "";
}

/* ── 参考音频列表 ─────────────────────────────────────── */
let refList = [];

async function fillRefList() {
  try {
    refList = await api().list_ref_audios();
  } catch (e) {
    refList = [];
  }
  const sel = $("refSel");
  const keep = (S.cfg && S.cfg.ref_audio) || sel.value;
  sel.innerHTML = "";
  if (!refList.length) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = t("（没找到参考音频，点「浏览…」选一个）");
    sel.appendChild(o);
    return;
  }
  // 按模型分组：挑参考音频其实是在挑「用谁的腔调说话」，
  // 一长条平铺列表里分不清哪条属于谁。组名和后缀都尽量给中文。
  const order = [];
  const groups = {};
  for (const it of refList) {
    const k = it.model || "";
    if (!groups[k]) { groups[k] = []; order.push(k); }
    groups[k].push(it);
  }
  const keys = order.filter((k) => k).sort();
  if (groups[""]) keys.push("");
  for (const k of keys) {
    const list = groups[k];
    const g = document.createElement("optgroup");
    const zh = list[0].model_zh || "";
    if (!k) {
      g.label = t("通用音频（没有专属样本时，任意干净人声都能顶替）");
    } else {
      g.label = zh && zh !== k ? zh + "（" + k + "）" : k;
    }
    for (const it of list) {
      const o = document.createElement("option");
      o.value = it.path;
      const tag = it.scene ? "[" + it.scene + "] "
        : (it.no ? "[" + it.no + "] " : "");
      // 通用音频没有原文，只剩一长串切片文件名，截短点免得把下拉撑爆
      const label = it.text ? it.text.slice(0, 22) : it.name.slice(0, 26);
      o.textContent = tag + label + "  " + it.dur + "s";
      o.title = it.path;
      g.appendChild(o);
    }
    sel.appendChild(g);
  }
  // 顺带说一句都有哪些角色的样本可用，不然要一条条翻
  const own = keys.filter((k) => k);
  const sampleCount = own.reduce((n, k) => n + groups[k].length, 0);
  const parts = own.map((k) => {
    const zh = (groups[k][0] && groups[k][0].model_zh) || k;
    return zh + " " + groups[k].length;
  });
  addLog("[参考] 训练样本 " + sampleCount + " 条" +
    (parts.length ? "（" + parts.join("、") + "）" : "") +
    (refList.length > sampleCount
      ? "，另有通用音频 " + (refList.length - sampleCount) + " 条" : ""));
  const hit = refList.find((x) => x.path === keep);
  sel.value = hit ? hit.path : refList[0].path;

  // 启动时也按当前模型对一次：手上拿的是别的角色的参考，音色会夹。
  // 模型名要从路径的文件名里取，下拉框文字带着 [GPT_weights_v2Pro] 这类后缀，截不准
  const gptPath0 = S.modelMap[$("selGpt").value] || S.cfg.gpt_path || "";
  const base0 = modelKeyOf(gptPath0);
  // 自动选中的那条取时长最接近五秒的：语气最中性，也最贴近训练时的分布。
  // 列表里把战斗、礼物这类有辨识度的排前面是给人挑的，默认值不必是它们
  const mine = refList
    .filter((x) => x.model && x.model.toLowerCase() === base0)
    .sort((a, b) => Math.abs(a.dur - 5) - Math.abs(b.dur - 5))[0];
  const cur = refList.find((x) => x.path === sel.value);

  if (mine && (!cur || cur.model !== mine.model)) {
    sel.value = mine.path;
    if (mine.text) {
      $("promptText").value = mine.text;
      $("selPLang").value = mine.lang || "ja";
      S.cfg.prompt_text = mine.text;
      S.cfg.prompt_lang = mine.lang || "ja";
    }
    S.cfg.ref_audio = mine.path;
    api().update_cfg({
      ref_audio: mine.path,
      prompt_text: S.cfg.prompt_text || "",
      prompt_lang: S.cfg.prompt_lang || "ja",
    });
    addLog("[参考] 当前模型是 " + (mine.model_zh || base0) + "，自动用了它的训练样本当参考");
  }
}

/* ── 下拉框 ───────────────────────────────────────────── */
function fillSelect(sel, values, labelOf) {
  const keep = sel.value;
  sel.innerHTML = "";
  for (const v of values) {
    const o = document.createElement("option");
    o.value = v;                              // 值是后端认的字面量，不翻译
    o.textContent = labelOf ? labelOf(v) : v; // 显示名才跟着语言走
    sel.appendChild(o);
  }
  if (values.includes(keep)) sel.value = keep;
}

/* 值和显示分开的版本：后端要代码（ja），人要中文（日语） */
function fillSelectPairs(sel, pairs) {
  const keep = sel.value;
  sel.innerHTML = "";
  // 循环变量别叫 t：那会遮住全局的翻译函数，调用时不报错但结果全错
  for (const [v, label] of pairs) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = label;
    sel.appendChild(o);
  }
  const vals = pairs.map((p) => p[0]);
  if (vals.includes(keep)) sel.value = keep;
}

function fillModels(models) {
  S.models = models || { gpt: [], sovits: [] };
  S.modelMap = {};
  const g = $("selGpt"), s = $("selSovits");
  const build = (sel, items, saved) => {
    sel.innerHTML = "";
    if (!items.length) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = t("（没扫到权重）");
      sel.appendChild(o);
      return;
    }
    let picked = "";
    for (const it of items) {
      S.modelMap[it.label] = it.path;
      const o = document.createElement("option");
      o.value = it.label;
      o.textContent = it.label;
      sel.appendChild(o);
      if (it.path === saved) picked = it.label;
    }
    sel.value = picked || items[0].label;
  };
  build(g, S.models.gpt || [], S.cfg.gpt_path || "");
  build(s, S.models.sovits || [], S.cfg.sovits_path || "");
}

/* ── 控件填充 ─────────────────────────────────────────── */
function fillControls() {
  const c = S.cfg || {};
  fillSelectPairs($("selPLang"), langPairs());
  fillSelectPairs($("selTLang"), langPairs());
  fillSelect($("selSplit"), SPLITS);
  fillSelect($("selDevice"), DEVICES, t);

  $("gsvDir").value = c.gsv_dir || "";
  $("promptText").value = c.prompt_text || "";
  $("mainText").value = c.text || "";
  $("selPLang").value = c.prompt_lang || "ja";
  $("selTLang").value = c.text_lang || "ja";
  $("selSplit").value = c.text_split_method || "cut0";
  $("pTopK").value = c.top_k != null ? c.top_k : 15;
  $("pTopP").value = c.top_p != null ? c.top_p : 1.0;
  $("pTemp").value = c.temperature != null ? c.temperature : 1.0;
  $("pRep").value = c.repetition_penalty != null ? c.repetition_penalty : 1.35;
  $("pSeed").value = c.seed != null ? c.seed : 42;
  $("pRand").checked = !!c.random_seed;
  fillModels(S.models);
}

function collect() {
  return {
    gsv_dir: $("gsvDir").value.trim(),
    ref_audio: $("refSel").value, 
    prompt_text: $("promptText").value,
    prompt_lang: $("selPLang").value,
    text: $("mainText").value,
    text_lang: $("selTLang").value,
    text_split_method: $("selSplit").value,
    random_seed: $("pRand").checked,
    top_k: Number($("pTopK").value) || 15,
    top_p: Number($("pTopP").value) || 1.0,
    temperature: Number($("pTemp").value) || 1.0,
    repetition_penalty: Number($("pRep").value) || 1.35,
    seed: Number($("pSeed").value) || 42,
    gpt_path: S.modelMap[$("selGpt").value] || "",
    sovits_path: S.modelMap[$("selSovits").value] || "",
  };
}

async function pushCfg() {
  const patch = collect();
  S.cfg = await api().update_cfg(patch);
  return S.cfg;
}

/* ── 背景轮播 ─────────────────────────────────────────── */
async function startBg() {
  let list = [];
  try {
    list = await api().bg_images();
  } catch (e) {
    list = [];
  }
  if (!list || !list.length) return;
  S.bg.list = list;
  S.bg.idx = 0;
  const a = $("bgA"), b = $("bgB");
  a.style.backgroundImage = 'url("' + fileUrl(list[0]) + '")';
  a.classList.add("on");
  let cur = a;
  if (S.bg.timer) clearInterval(S.bg.timer);
  S.bg.timer = setInterval(() => {
    if (S.bg.list.length < 2) return;
    S.bg.idx = (S.bg.idx + 1) % S.bg.list.length;
    const next = cur === a ? b : a;
    next.style.backgroundImage = 'url("' + fileUrl(S.bg.list[S.bg.idx]) + '")';
    next.classList.add("on");
    cur.classList.remove("on");
    cur = next;
  }, 9000);
}

/* ── 波形 / 频谱 ──────────────────────────────────────── */
function drawWave(playFrac) {
  const cv = $("waveCanvas");
  if (!cv) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  const peaks = S.wave || [];
  if (!peaks.length) {
    // 没有音频就画一条安静的中线。以前这里铺了一排小色块当装饰，
    // 看着像已经有波形了，实际是假的，容易误以为合成过了
    ctx.strokeStyle = "rgba(57,255,209,0.20)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(1, h / 2);
    ctx.lineTo(w - 1, h / 2);
    ctx.stroke();
    return;
  }
  const n = peaks.length;
  const bw = (w - 2) / n;
  const frac = playFrac == null ? 0 : playFrac;
  for (let i = 0; i < n; i++) {
    const p = Math.max(0.02, Math.min(1, peaks[i] || 0));
    const bh = Math.max(3, p * (h - 6));
    const x = 1 + i * bw;
    const played = (i / n) <= frac;
    ctx.fillStyle = played ? "#39ffd1" : "rgba(57,255,209,0.28)";
    ctx.fillRect(x, (h - bh) / 2, Math.max(1.4, bw * 0.62), bh);
  }
  if (frac > 0) {
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    ctx.fillRect(1 + frac * (w - 2), 0, 1.5, h);
  }
}

function drawSpec(tSec) {
  const cv = $("specCanvas");
  if (!cv) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  const spec = S.spec;
  if (!spec || !spec.level || !spec.level.length) {
    // 同样只留一条底线，别拿装饰柱冒充频谱
    ctx.strokeStyle = "rgba(57,255,209,0.14)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(1, h - 1);
    ctx.lineTo(w - 1, h - 1);
    ctx.stroke();
    return;
  }
  const level = spec.level;
  const fps = spec.fps || 25;
  let frame = Math.floor((tSec || 0) * fps);
  frame = Math.max(0, Math.min(level.length - 1, frame));
  const row = level[frame] || [];
  const bands = row.length || 32;
  const gap = 2;
  const bw = (w - 2 - gap * (bands - 1)) / bands;
  for (let i = 0; i < bands; i++) {
    const v = Math.max(0.02, Math.min(1, row[i] || 0));
    const bh = Math.max(2, v * (h - 4));
    const x = 1 + i * (bw + gap);
    const g = ctx.createLinearGradient(0, h - bh, 0, h);
    g.addColorStop(0, "rgba(57,255,209,0.95)");
    g.addColorStop(1, "rgba(35,201,163,0.35)");
    ctx.fillStyle = g;
    ctx.fillRect(x, h - bh, bw, bh);
  }
}

/* ── 系统监控 ─────────────────────────────────────────── */
function paintMonitor(m) {
  const cpu = m.cpu || {};
  const gpu = m.gpu;
  $("cpuLine").textContent = (cpu.name || t("处理器")) +
    "   " + Math.round(cpu.pct || 0) + "%   " +
    ((cpu.mhz || 0) / 1000).toFixed(2) + " GHz";
  if (gpu) {
    $("gpuLine").textContent = (gpu.name || t("显卡")) +
      "   " + gpu.pct + "%   " + gpu.ghz + " GHz   " + gpu.temp + "°C   " +
      gpu.mem + "/" + gpu.total + " GB";
  } else {
    $("gpuLine").textContent = m.gpu_ok ? t("读取中…") : t("未检测到独立显卡");
  }
  drawMonitor(cpu.hist || [], (gpu && gpu.hist) || []);
}

function drawMonitor(cpuHist, gpuHist) {
  const cv = $("monCanvas");
  if (!cv) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(110,140,175,0.14)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  const line = (hist, color) => {
    if (!hist || hist.length < 2) return;
    ctx.beginPath();
    for (let i = 0; i < hist.length; i++) {
      const x = (i / (hist.length - 1)) * w;
      const y = h - (Math.min(100, hist[i]) / 100) * (h - 4) - 2;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.stroke();
  };
  line(cpuHist, "#39ffd1");
  line(gpuHist, "#3a7bff");
}

/* ── 历史 ─────────────────────────────────────────────── */
function addHistory(row) {
  if (!row) return;
  S.lastWav = row.path || S.lastWav;
  $("info").textContent = row.file + "  ｜ " + row.dur + "s ｜ 耗时 " + row.cost + "s ｜ seed=" + row.seed;
  const tb = $("histBody");
  const tr = document.createElement("tr");
  tr.className = "flash";
  tr.dataset.path = row.path || "";
  tr.dataset.text = row.text || "";
  tr.innerHTML = "<td>" + esc(row.time) + "</td><td title='" + esc(row.text) + "'>" +
    esc((row.text || "").replace(/\s+/g, " ").slice(0, 40) || "(空)") +
    "</td><td>" + row.dur + "s</td><td>" + esc(row.file) + "</td>";
  tr.addEventListener("dblclick", () => play(tr.dataset.path));
  tr.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    openInFolder(tr.dataset.path);
  });
  tb.insertBefore(tr, tb.firstChild);
  setTimeout(() => tr.classList.remove("flash"), 900);
  play(row.path);
}

function renderHistory(rows) {
  const tb = $("histBody");
  tb.innerHTML = "";
  (rows || []).slice().reverse().forEach(addHistory);
}

/* ── 播放 ─────────────────────────────────────────────── */
async function play(path) {
  if (!path) return;
  const audio = $("player");
  audio.src = fileUrl(path);
  S.playing = path;
  try {
    await audio.play();
  } catch (e) {
    addLog("[播放] 浏览器拒绝播放：" + path);
  }
  try {
    S.wave = await api().wave_data(path);
  } catch (e) {
    S.wave = [];
  }
  try {
    S.spec = await api().spectrum_data(path);
  } catch (e) {
    S.spec = null;
  }
  drawWave(0);
  drawSpec(0);
}

function tickPlayback() {
  const audio = $("player");
  // 暂停就收工，别让空转的 rAF 一直烧 CPU
  if (audio.paused) return;
  const d = audio.duration;
  // 刚触发 play 的那一瞬间 duration 还是 NaN，拿不到就继续等下一帧。
  // 以前这里是直接 return 且不再调度，结果就是波形永远停在第一帧。
  if (isFinite(d) && d > 0) {
    drawWave(audio.currentTime / d);
    drawSpec(audio.currentTime);
  }
  requestAnimationFrame(tickPlayback);
}

const player = $("player");
player.addEventListener("play", () => requestAnimationFrame(tickPlayback));
player.addEventListener("loadedmetadata", () => {
  if (!player.paused) requestAnimationFrame(tickPlayback);
});
player.addEventListener("ended", () => {
  drawWave(1);
  drawSpec(isFinite(player.duration) ? player.duration : 0);
});
player.addEventListener("pause", () => {
  drawSpec(player.currentTime || 0);
});

/* ── 弹层 ─────────────────────────────────────────────── */
function modal(title, html, okText, okFn, cancelText, cancelFn) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  const ok = $("modalOk"), cancel = $("modalCancel");
  ok.textContent = okText || t("知道了");
  ok.onclick = () => { if (okFn) setTimeout(okFn, 0); };
  if (cancelText) {
    cancel.textContent = cancelText;
    cancel.style.display = "";
    cancel.onclick = () => { if (cancelFn) setTimeout(cancelFn, 0); };
  } else {
    cancel.style.display = "none";
    cancel.onclick = null;
  }
  $("modalMask").classList.add("on");
}
$("modalOk").addEventListener("click", () => $("modalMask").classList.remove("on"));
$("modalCancel").addEventListener("click", () => $("modalMask").classList.remove("on"));
$("modalMask").addEventListener("click", (e) => {
  if (e.target === $("modalMask")) $("modalMask").classList.remove("on");
});

/* ── 交互绑定 ─────────────────────────────────────────── */
async function doApplyPreset(name) {
  const r = await api().apply_preset(name);
  if (r.ok) {
    const st = await api().get_state();
    S.cfg = st.cfg;
    fillControls();
    $("modalMask").classList.remove("on");
    addLog("[组合] " + r.msg);
    if (S.ready) api().apply_model();
  } else {
    addLog("[组合] " + r.msg);
  }
}

async function bindUI() {
  $("btnBrowse").onclick = async () => {
    const r = await api().pick_folder("gsv");
    if (r.ok) {
      const st = await api().get_state();
      S.cfg = st.cfg;
      fillControls();
      S.models = r.models || st.models;
      fillModels(S.models);
    } else if (r.msg && r.msg !== "取消") {
      modal(t("目录不对"), esc(r.msg));
    }
  };

  $("btnAuto").onclick = async () => {
    const r = await api().auto_detect();
    if (!r.ok) {
      modal(t("没找到"), t("常见位置都没找到 GPT-SoVITS 便携包，请手动点「浏览」选目录。"));
      return;
    }
    if (r.found.length === 1) {
      const rr = await api().set_gsv_dir(r.found[0]);
      if (rr.ok) {
        const st = await api().get_state();
        S.cfg = st.cfg;
        fillControls();
        S.models = rr.models || st.models;
        fillModels(S.models);
      }
    } else {
      const list = r.found.map((p) =>
        '<div class="preset"><span class="detail">' + esc(p) + "</span>" +
        '<button class="btn accent" data-p="' + esc(p) + '">用这个</button></div>').join("");
      modal(t("找到多个"), '<div class="preset-list">' + list + "</div>");
      $("modalBody").querySelectorAll("button[data-p]").forEach((b) => {
        b.onclick = async () => {
          const rr = await api().set_gsv_dir(b.dataset.p);
          if (rr.ok) {
            const st = await api().get_state();
            S.cfg = st.cfg;
            fillControls();
            S.models = rr.models || st.models;
            fillModels(S.models);
            $("modalMask").classList.remove("on");
          }
        };
      });
    }
  };

  $("btnStart").onclick = async () => {
    await pushCfg();
    const r = await api().start_service();
    if (r.reused) {
      // 端口上那个不是这边起的，进度读不到。问一句要不要接管，别自作主张杀别人的进程
      modal(t("端口上已经有服务"),
        t("端口 {port} 上已经有一个 GPT-SoVITS 服务{pid}，它不是这个界面启动的。",
          { port: r.port || "", pid: r.pid ? "（进程 " + r.pid + "）" : "" }) +
        "<br><br>" +
        t("共用它照样能合成，但加载模型和合成的进度都读不到，进度条只能按字数估算。") + "<br>" +
        t("接管会先把这个进程关掉，再用这里的运行环境重新启动一份，进度就准了，代价是模型要重新加载一次。"),
        t("接管并重启"), async () => {
          // 变量别叫 t：那是全局翻译函数的名字，遮住之后这个回调里的文字全对不上
          const rv = await api().takeover_service();
          if (!rv.ok) modal(t("接管服务"), esc(rv.msg));
        },
        t("先共用着"), null);
      return;
    }
    if (!r.ok) modal(t("启动服务"), esc(r.msg));
  };
  $("btnStop").onclick = () => api().stop_service();

  $("btnRefresh").onclick = async () => {
    await pushCfg();
    const m = await api().refresh_models();
    fillModels(m);
  };

  $("btnApplyModel").onclick = async () => {
    // 换模型时把参考音频也带过去，不然会拿着上一个角色的样本去合成，
    // 音色是新的、腔调是旧的，还可能因为样本太短直接 400
    await followModel();
    await pushCfg();
    const r = await api().apply_model();
    if (!r.ok) modal(t("应用模型"), esc(r.msg));
  };

  $("btnPresets").onclick = async () => {
    const list = await api().get_presets();
    if (!list.length) {
      modal(t("已存组合"), '<div class="empty">' + t("还没有绑定过组合。") + "<br>" +
        t("在左边选好模型和参考音频，点「绑定到当前模型」，这里就会出现一条。") +
        "<br>" + t("换机器或换目录时，绑定的文件找不到会自动隐藏，不会留一条点不动的废记录。") + "</div>");
      return;
    }
    const html = '<div class="preset-list">' + list.map((p) =>
      '<div class="preset"><span class="name">' + esc(p.name) + "</span>" +
      '<span class="detail">' + esc(p.ref ? p.ref.split(/[\\/]/).pop() : t("无参考")) + "</span>" +
      '<button class="btn accent" data-n="' + esc(p.name) + '">' + t("套用") + '</button></div>').join("") + "</div>";
    modal(t("已存组合"), html);
    $("modalBody").querySelectorAll("button[data-n]").forEach((b) => {
      b.onclick = () => doApplyPreset(b.dataset.n);
    });
  };

  $("refSel").onchange = async () => {
    const path = $("refSel").value;
    const it = refList.find((x) => x.path === path);
    const patch = { ref_audio: path };
    // 训练样本自带原文，选的时候一起填好，省得音频和文字对不上
    if (it && it.text) {
      $("promptText").value = it.text;
      $("selPLang").value = it.lang || "ja";
      patch.prompt_text = it.text;
      patch.prompt_lang = it.lang || "ja";
      addLog("[参考] " + (it.model ? (it.model_zh || it.model) + " 的训练样本，参考文本已跟着填好" : "已切换参考音频"));
    } else {
      addLog("[参考] 切到 " + ((it && it.name) || path));
    }
    await api().update_cfg(patch);
    S.cfg.ref_audio = path;
    if (patch.prompt_text) S.cfg.prompt_text = patch.prompt_text;
  };

  // 换模型时，直接跳到这个模型自己的训练样本，音色才对得上
  const followModel = async () => {
    const gptPath = S.modelMap[$("selGpt").value] || S.cfg.gpt_path || "";
    const base = modelKeyOf(gptPath);
    if (!base) return;
    const hit = refList
      .filter((x) => x.model && x.model.toLowerCase() === base)
      .sort((a, b) => Math.abs(a.dur - 5) - Math.abs(b.dur - 5))[0];
    if (!hit || S.cfg.ref_audio === hit.path) return;
    $("refSel").value = hit.path;
    $("promptText").value = hit.text || "";
    if (hit.lang) $("selPLang").value = hit.lang;
    await api().update_cfg({
      ref_audio: hit.path,
      prompt_text: hit.text || "",
      prompt_lang: hit.lang || "ja",
    });
    S.cfg.ref_audio = hit.path;
    addLog("[参考] 跟着模型换成 " + (hit.model_zh || hit.model) + " 的训练样本");
  };
  $("selGpt").onchange = followModel;
  $("selSovits").onchange = followModel;

  // 挑语气得先听得出来，不然要合成一次才知道选错没有
  $("btnPreviewRef").onclick = () => {
    const path = $("refSel").value;
    if (!path) return;
    play(path);
    addLog("[参考] 试听当前参考音频");
  };

  $("btnPickRef").onclick = async () => {
    const r = await api().pick_file("ref");
    if (!r.ok) return;
    await api().update_cfg({ ref_audio: r.path });
    S.cfg.ref_audio = r.path;
    await fillRefList();
    $("refSel").value = r.path;
  };

  $("btnApplyRef").onclick = async () => {
    await pushCfg();
    const r = await api().apply_ref();
    if (!r.ok) modal(t("应用参考"), esc(r.msg));
  };

  $("btnBindRef").onclick = async () => {
    await pushCfg();
    const r = await api().bind_ref();
    $("refState").textContent = r.ok
      ? t("参考：已绑定到当前模型")
      : t("参考：未绑定（换模型不会自动换参考）");
  };

  $("btnSynth").onclick = async () => {
    await pushCfg();
    const r = await api().synth();
    if (r.ok) return;
    if (r.suggest_ref) {
      // 参考音频不合格时后端会挑好一条同角色的，这里给个一键换上的口子
      modal(t("合成"), esc(r.msg), t("换成这条再试"), async () => {
        $("refSel").value = r.suggest_ref;
        await $("refSel").onchange();
      }, t("先算了"), null);
      return;
    }
    modal(t("合成"), esc(r.msg));
  };

  $("btnPlay").onclick = () => play(S.lastWav);
  $("btnSaveAs").onclick = async () => {
    const r = await api().save_as();
    if (!r.ok && r.msg !== "取消") modal(t("另存为"), esc(r.msg));
  };
  $("btnOpenOut").onclick = () => api().open_output();

  $("btnCheck").onclick = async () => {
    const items = await api().self_check();
    // 第四项是「必需」标记：缺了会让人没法用的标红，可选项缺了只灰一下。
    // 不然第一次打开的人看到一屏叉，会以为整个程序坏了。
    const html = '<div class="check-list">' + items.map((it) => {
      const [name, ok, detail, required] = it;
      const must = required !== false;
      const cls = ok ? "ok" : must ? "bad" : "opt";
      const mark = ok ? "✓" : must ? "✕" : "–";
      return '<div class="check-item ' + cls + '">' +
        '<span class="mark">' + mark + "</span>" +
        "<span>" + esc(t(name)) + '</span><span class="detail">' + esc(t(detail)) + "</span></div>";
    }).join("") + "</div>";
    modal(t("自检"), html);
  };

  $("btnExport").onclick = async () => {
    const r = await api().export_config();
    modal(t("导出配置"), "<div class='empty'>" +
      t("把下面这段复制走，换机器时用「导入配置」贴回来。") + "</div>" +
      "<textarea class='ta' rows='14' readonly style='margin-top:8px'>" + esc(r.data) + "</textarea>");
  };

  $("btnImport").onclick = () => {
    const html = "<div class='empty'>" + t("把之前导出的那段配置贴进来：") + "</div>" +
      "<textarea class='ta' rows='12' id='impBox' style='margin-top:8px'></textarea>";
    modal(t("导入配置"), html);
    $("modalOk").textContent = t("导入");
    $("modalOk").onclick = async () => {
      const text = $("impBox").value;
      const r = await api().import_config(text);
      if (!r.ok) {
        $("modalBody").insertAdjacentHTML("beforeend",
          "<div style='color:var(--err);margin-top:8px'>" + esc(r.msg) + "</div>");
        return;
      }
      S.cfg = r.snapshot.cfg;
      S.models = r.snapshot.models;
      fillControls();
      fillModels(S.models);
      $("modalMask").classList.remove("on");
      $("modalOk").textContent = t("知道了");
      $("modalOk").onclick = () => $("modalMask").classList.remove("on");
    };
  };

  $("btnBg").onclick = async () => {
    const r = await api().pick_bg_folder();
    if (r.ok && r.images) {
      addLog("[背景] " + r.msg);
      await startBg();
    }
  };
  $("btnBg").oncontextmenu = async (e) => {
    e.preventDefault();
    const r = await api().reset_bg();
    if (r.ok) {
      addLog("[背景] " + r.msg);
      await startBg();
    }
  };

  $("selDevice").onchange = async () => {
    const r = await api().set_device($("selDevice").value);
    $("devHint").textContent = r.msg || "";
    if (!r.ok) modal(t("切换设备"), esc(r.msg));
  };

  $("btnBatchEdit").onclick = async () => {
    const st = await api().get_state();
    const rows = (st.batch_lines || []).map((r) => r[0] + "|" + r[1]).join("\n");
    const html = "<div class='empty'>" + t("每行一条：文件名|台词。留空则不生成该条。") + "</div>" +
      "<textarea class='ta' rows='12' id='batchBox' style='margin-top:8px'>" + esc(rows) + "</textarea>";
    modal(t("编辑批量台词"), html);
    $("modalOk").textContent = t("保存");
    $("modalOk").onclick = async () => {
      const list = [];
      for (const line of $("batchBox").value.split("\n")) {
        const s = line.trim();              // 别用 t 当变量名，那是翻译函数
        if (!s || !s.includes("|")) continue;
        const i = s.indexOf("|");
        list.push([s.slice(0, i).trim(), s.slice(i + 1).trim()]);
      }
      await api().update_cfg({ batch_lines: list });
      addLog("[批量] 台词已保存，共 " + list.length + " 条");
      $("modalMask").classList.remove("on");
      $("modalOk").textContent = t("知道了");
      $("modalOk").onclick = () => $("modalMask").classList.remove("on");
    };
  };

  $("btnBatchRun").onclick = async () => {
    const r = await api().batch_run();
    if (r && !r.ok) modal(t("批量替换"), esc(r.msg || t("没开始")));
  };

  $("chkFx").onchange = () => {
    document.body.classList.toggle("no-fx", !$("chkFx").checked);
  };

  window.addEventListener("resize", () => {
    drawWave(0);
    drawMonitor([], []);
  });
}

/* ── 启动 ─────────────────────────────────────────────── */
async function init() {
  await bindUI();
  let st = null;
  try {
    st = await api().get_state();
  } catch (e) {
    addLog("[启动] 后端还没就绪：" + e);
    return;
  }
  S.cfg = st.cfg || {};
  S.models = st.models || { gpt: [], sovits: [] };
  S.history = st.history || [];
  S.lastWav = st.last_wav || "";
  S.ready = !!st.ready;
  S.busy = !!st.busy;
  // 界面语言跟着配置走：第一次打开是中文，切过之后记住
  initLangSelect();
  setLang(S.cfg.ui_lang || I18N_CUR);
  fillControls();
  await fillRefList();
  renderHistory(S.history);
  syncButtons();
  await startBg();
  const askDevice = async () => {
    try {
      const dev = await api().device_state();
      $("selDevice").value = DEVICES.includes(dev.label) ? dev.label : DEVICES[0];
      $("devHint").textContent = dev.gpu_ok
        ? (dev.gpu_name || t("已识别独显"))
        : t("无独显，只能 CPU");
    } catch (e) { /* 忽略 */ }
  };
  // GPU 探测要跑一次 nvidia-smi，头一秒问到的永远是没独显
  setTimeout(askDevice, 1500);
  drawWave(0);
  drawSpec(0);
  drawMonitor([], []);
  setStatus(t("服务未启动"), "");
  // 浏览器偶尔会因为某个输入框把页面卷到中间，复位一下
  window.scrollTo(0, 0);
  const sc = document.querySelector(".main");
  if (sc) sc.scrollTop = 0;
}

/* 后端事件轮询：pywebview 的 evaluate_js 不能跨线程，所以反过来让前端来拉 */
function startPolling() {
  let running = false;
  setInterval(async () => {
    if (running) return;
    running = true;
    try {
      const events = await api().poll();
      if (events && events.length) {
        for (const e of events) window.__push(e);
      }
    } catch (e) { /* 窗口正在关 */ }
    running = false;
  }, 120);
}

window.addEventListener("pywebviewready", () => {
  init();
  startPolling();
});
