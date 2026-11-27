/**
 * 拼豆工坊 · BeadCraft Studio (1930s Rubber Hose Edition)
 * 深度集成 finktheartist/rubber-hose-ui 橡皮管卡通组件体系 (<hose-tabs>, <hose-toggle>, <hose-slider>, <hose-button>, <hose-toast>)
 * 与专属拼豆精灵 (<hose-bead-mascot>)、AI 联网对话智能体及微信 ClawBot 扫码实时同步
 */

const STORAGE_PREFIX = "beadcraft_done_v1:";

const state = {
  imageId: null,
  sourceImgObj: null,
  tiers: {},                // { simple: pattern, hd: pattern, faithful: pattern }
  defaultMaxSides: { simple: 32, hd: 58, faithful: 100 },
  activeQuality: "hd",
  paletteId: "mard_96",
  removeBg: false,
  bgTolerance: 19,
  skillLevel: "standard",   // beginner | standard | pro
  beadSpec: "mini_26mm",    // mini_26mm | standard_50mm
  viewMode: "ring",         // ring | code | flat | compare
  leftMode: "agent",        // agent | manual
  activeTool: "pan",        // pan | brush | eraser | picker
  selectedColorIdx: 0,
  spotlightColorIdx: null,
  bomFilter: "",
  bomSort: "count",
  completedByTier: { simple: new Set(), hd: new Set(), faithful: new Set() },
  undoStacks: { simple: [], hd: [], faithful: [] },
  redoStacks: { simple: [], hd: [], faithful: [] },
  manualEditsByTier: { simple: false, hd: false, faithful: false },

  // AI 对话智能体与微信 ClawBot 状态
  agentConfig: null,
  agentBusy: false,
  chatMessages: [],
  recentCandidates: [],
  wechatStatus: null,
  wechatPollTimer: null,

  showBoard29: true,
  showRuler: true,
  daylightMat: true,        // 默认启用 1930s 复古羊皮纸赛璐璐拼板底色
  filmEnabled: true,        // 默认启用 1930s 老胶片颗粒与轻微灰尘层
  craftFocus: false,

  // 视口与交互状态
  zoom: 1.0,
  panX: 0,
  panY: 0,
  baseCellPx: 20,
  isDragging: false,
  isPainting: false,
  spacePressed: false,
  dragStartX: 0,
  dragStartY: 0,
  dirtyStroke: false,
  strokeSnapshot: null,
};

const els = {
  workspaceGrid: document.getElementById("workspaceGrid"),
  btnFilmMode: document.getElementById("btnFilmMode"),
  filmModeLabel: document.getElementById("filmModeLabel"),
  filmOverlay: document.getElementById("filmOverlay"),
  btnOpenWechatBot: document.getElementById("btnOpenWechatBot"),
  wechatStatusDot: document.getElementById("wechatStatusDot"),
  btnQuickWechat: document.getElementById("btnQuickWechat"),
  btnOpenAgentConfig: document.getElementById("btnOpenAgentConfig"),
  agentStatusDot: document.getElementById("agentStatusDot"),
  btnCraftFocus: document.getElementById("btnCraftFocus"),
  craftFocusLabel: document.getElementById("craftFocusLabel"),

  // Rubber Hose 交互角色元素
  hoseLeftTabs: document.getElementById("hoseLeftTabs"),
  hoseSendBtn: document.getElementById("hoseSendBtn"),
  hoseRemoveBg: document.getElementById("hoseRemoveBg"),
  hoseToggleSaid: document.getElementById("hoseToggleSaid"),
  hoseSizeSlider: document.getElementById("hoseSizeSlider"),
  hoseBeadMascot: document.getElementById("hoseBeadMascot"),
  mascotSpeech: document.getElementById("mascotSpeech"),
  hoseToaster: document.getElementById("hoseToaster"),

  agentPane: document.getElementById("agentPane"),
  manualPane: document.getElementById("manualPane"),
  agentModelTag: document.getElementById("agentModelTag"),
  btnQuickConfig: document.getElementById("btnQuickConfig"),
  chatHistory: document.getElementById("chatHistory"),
  agentChatForm: document.getElementById("agentChatForm"),
  agentPromptInput: document.getElementById("agentPromptInput"),
  btnSendPrompt: document.getElementById("btnSendPrompt"),

  // 微信 ClawBot 扫码弹窗元素
  wechatClawDialog: document.getElementById("wechatClawDialog"),
  btnCloseWechatIcon: document.getElementById("btnCloseWechatIcon"),
  btnCloseWechatFooter: document.getElementById("btnCloseWechatFooter"),
  wechatStateBadge: document.getElementById("wechatStateBadge"),
  wechatBotMeta: document.getElementById("wechatBotMeta"),
  btnRefreshWechatQr: document.getElementById("btnRefreshWechatQr"),
  btnDisconnectWechat: document.getElementById("btnDisconnectWechat"),
  wechatQrSection: document.getElementById("wechatQrSection"),
  wechatQrImg: document.getElementById("wechatQrImg"),
  wechatQrLoading: document.getElementById("wechatQrLoading"),
  wechatLiveHint: document.getElementById("wechatLiveHint"),
  wechatVerifyWrap: document.getElementById("wechatVerifyWrap"),
  wechatVerifyInput: document.getElementById("wechatVerifyInput"),
  btnSubmitVerifyCode: document.getElementById("btnSubmitVerifyCode"),
  wechatConnectedSection: document.getElementById("wechatConnectedSection"),
  wechatBoundIds: document.getElementById("wechatBoundIds"),
  wechatErrorBox: document.getElementById("wechatErrorBox"),

  // 配置弹窗元素
  agentConfigDialog: document.getElementById("agentConfigDialog"),
  agentConfigForm: document.getElementById("agentConfigForm"),
  btnCloseConfigIcon: document.getElementById("btnCloseConfigIcon"),
  btnCancelConfig: document.getElementById("btnCancelConfig"),
  cfgPresetSelect: document.getElementById("cfgPresetSelect"),
  cfgProtocolSelect: document.getElementById("cfgProtocolSelect"),
  cfgBaseUrl: document.getElementById("cfgBaseUrl"),
  cfgModelName: document.getElementById("cfgModelName"),
  cfgApiKey: document.getElementById("cfgApiKey"),
  cfgLlmSavedHint: document.getElementById("cfgLlmSavedHint"),
  btnTestLlm: document.getElementById("btnTestLlm"),
  llmTestResult: document.getElementById("llmTestResult"),
  cfgTavilyKey: document.getElementById("cfgTavilyKey"),
  cfgTavilySavedHint: document.getElementById("cfgTavilySavedHint"),
  cfgTavilyDepth: document.getElementById("cfgTavilyDepth"),
  cfgBackupImg: document.getElementById("cfgBackupImg"),
  btnTestTavily: document.getElementById("btnTestTavily"),
  tavilyTestResult: document.getElementById("tavilyTestResult"),
  cfgProxyMode: document.getElementById("cfgProxyMode"),
  cfgCustomProxyField: document.getElementById("cfgCustomProxyField"),
  cfgCustomProxy: document.getElementById("cfgCustomProxy"),

  fileInput: document.getElementById("fileInput"),
  dropzone: document.getElementById("dropzone"),
  sourceThumb: document.getElementById("sourceThumb"),
  imgDimBadge: document.getElementById("imgDimBadge"),
  sampleButtons: document.getElementById("sampleButtons"),
  paletteSelect: document.getElementById("paletteSelect"),
  chkRemoveBg: document.getElementById("chkRemoveBg"),
  bgTolWrap: document.getElementById("bgTolWrap"),
  bgTolRange: document.getElementById("bgTolRange"),
  bgTolVal: document.getElementById("bgTolVal"),
  customModifiedTag: document.getElementById("customModifiedTag"),
  customSizeRange: document.getElementById("customSizeRange"),
  customSizeVal: document.getElementById("customSizeVal"),
  btnResetSize: document.getElementById("btnResetSize"),
  btnBrushColor: document.getElementById("btnBrushColor"),
  brushSwatchDot: document.getElementById("brushSwatchDot"),
  brushColorCode: document.getElementById("brushColorCode"),
  palettePopover: document.getElementById("palettePopover"),
  paletteSearchInput: document.getElementById("paletteSearchInput"),
  fullPaletteGrid: document.getElementById("fullPaletteGrid"),
  btnUndo: document.getElementById("btnUndo"),
  btnRedo: document.getElementById("btnRedo"),
  btnBoard29Toggle: document.getElementById("btnBoard29Toggle"),
  btnRulerToggle: document.getElementById("btnRulerToggle"),
  btnPegboardMat: document.getElementById("btnPegboardMat"),
  matModeLabel: document.getElementById("matModeLabel"),
  canvasViewport: document.getElementById("canvasViewport"),
  canvas: document.getElementById("beadCanvas"),
  loadingBadge: document.getElementById("loadingBadge"),
  zoomLabel: document.getElementById("zoomLabel"),
  hoverInfo: document.getElementById("hoverInfo"),
  boardSummaryTag: document.getElementById("boardSummaryTag"),
  spotlightBanner: document.getElementById("spotlightBanner"),
  spotlightSwatch: document.getElementById("spotlightSwatch"),
  spotlightText: document.getElementById("spotlightText"),
  btnClearSpotlight: document.getElementById("btnClearSpotlight"),
  heroDuration: document.getElementById("heroDuration"),
  diffBadge: document.getElementById("diffBadge"),
  metricTotalBeads: document.getElementById("metricTotalBeads"),
  metricUniqueColors: document.getElementById("metricUniqueColors"),
  metricBoards: document.getElementById("metricBoards"),
  metricPhysSize: document.getElementById("metricPhysSize"),
  speedHint: document.getElementById("speedHint"),
  scatterHint: document.getElementById("scatterHint"),
  barPrep: document.getElementById("barPrep"),
  barPlace: document.getElementById("barPlace"),
  barDetail: document.getElementById("barDetail"),
  barIron: document.getElementById("barIron"),
  minPrep: document.getElementById("minPrep"),
  minPlace: document.getElementById("minPlace"),
  minDetail: document.getElementById("minDetail"),
  minIron: document.getElementById("minIron"),
  sessionAdvice: document.getElementById("sessionAdvice"),
  bomCountTag: document.getElementById("bomCountTag"),
  bomSearchInput: document.getElementById("bomSearchInput"),
  btnBomSort: document.getElementById("btnBomSort"),
  bomList: document.getElementById("bomList"),
  progressStrip: document.getElementById("progressStrip"),
  progressText: document.getElementById("progressText"),
  remainingTimeText: document.getElementById("remainingTimeText"),
  btnExportPng: document.getElementById("btnExportPng"),
  btnExportXlsx: document.getElementById("btnExportXlsx"),
  toast: document.getElementById("toast"),
};

const ctx = els.canvas.getContext("2d");

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inferToasterBrief(msg, isError) {
  if (isError) return "OOPS!";
  if (msg.includes("保存") || msg.includes("下载")) return "SAVED!";
  if (msg.includes("微信")) return "WECHAT!";
  if (msg.includes("色号") || msg.includes("吸取")) return "COLOR!";
  return "READY!";
}

function showToast(msg, isError = false) {
  els.toast.textContent = msg;
  els.toast.classList.toggle("error", Boolean(isError));
  els.toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => els.toast.classList.add("hidden"), isError ? 4200 : 2800);

  // 同步唤醒 Rubber Hose 烤面包机角色弹出吐司片 (DING!)
  if (els.hoseToaster && typeof els.hoseToaster.show === "function") {
    els.hoseToaster.show(msg, inferToasterBrief(msg, isError));
  }
}

function syncRemoveBgWidgets(checked) {
  els.chkRemoveBg.checked = Boolean(checked);
  if (els.hoseRemoveBg && "checked" in els.hoseRemoveBg) {
    els.hoseRemoveBg.checked = Boolean(checked);
  }
  if (els.hoseToggleSaid) {
    els.hoseToggleSaid.textContent = checked
      ? "灯泡已点亮！外围纯色背景已自动剔除"
      : "拨动右侧小灯泡，省去背景豆与工时";
  }
}

function syncSizeSliderWidgets(val) {
  els.customSizeRange.value = val;
  els.customSizeVal.textContent = val;
  if (els.hoseSizeSlider && "value" in els.hoseSizeSlider) {
    els.hoseSizeSlider.value = val;
  }
}

function setLoading(flag) {
  els.loadingBadge.classList.toggle("hidden", !flag);
}

function currentPattern() {
  return state.tiers[state.activeQuality] || null;
}

function activeCompletedSet() {
  return state.completedByTier[state.activeQuality];
}

function saveCompletedProgress() {
  if (!state.imageId) return;
  try {
    const key = `${STORAGE_PREFIX}${state.imageId}:${state.activeQuality}`;
    localStorage.setItem(key, JSON.stringify([...activeCompletedSet()]));
  } catch (_) {}
}

function restoreCompletedProgress(imageId) {
  for (const q of ["simple", "hd", "faithful"]) {
    state.completedByTier[q] = new Set();
    try {
      const raw = localStorage.getItem(`${STORAGE_PREFIX}${imageId}:${q}`);
      if (raw) {
        for (const v of JSON.parse(raw)) state.completedByTier[q].add(v);
      }
    } catch (_) {}
  }
}

function hasAnyManualEdits() {
  return Boolean(
    state.manualEditsByTier.simple || state.manualEditsByTier.hd || state.manualEditsByTier.faithful
  );
}

function confirmDiscardManualEdits(actionLabel) {
  if (!hasAnyManualEdits()) return true;
  return window.confirm(`当前图纸包含手工改色或擦除修改，${actionLabel}将重新生成并覆盖手工修改，是否继续？`);
}

function cloneGrid(grid) {
  return grid.map((row) => row.slice());
}

function switchLeftMode(mode) {
  state.leftMode = mode;
  document.querySelectorAll(".left-tab").forEach((btn) => {
    const isAct = btn.dataset.leftmode === mode;
    btn.classList.toggle("active", isAct);
    btn.setAttribute("aria-selected", String(isAct));
  });
  if (els.hoseLeftTabs && els.hoseLeftTabs.value !== mode) {
    els.hoseLeftTabs.value = mode;
  }
  els.agentPane.classList.toggle("hidden", mode !== "agent");
  els.manualPane.classList.toggle("hidden", mode !== "manual");
}

// ---------------------------------------------------------------------------
// 1930s 老动画胶片颗粒与灰尘划痕特效层（遵循 rubber-hose-ui 画廊设计，不对画布做位移）
// ---------------------------------------------------------------------------
function initVintageFilmOverlay() {
  const film = els.filmOverlay;
  if (!film || !window.RubberHose) return;
  const fx = window.RubberHose;
  const grain = film.querySelector(".grain");
  const dust = film.querySelector(".dust");
  const dg = dust.getContext("2d");

  const tile = document.createElement("canvas");
  tile.width = 200;
  tile.height = 200;
  const tx = tile.getContext("2d");
  const imgData = tx.createImageData(200, 200);
  const arr = imgData.data;
  for (let i = 0; i < arr.length; i += 4) {
    const v = 204 + Math.random() * 51;
    arr[i] = v;
    arr[i + 1] = v * 0.98;
    arr[i + 2] = v * 0.94;
    arr[i + 3] = 255;
  }
  tx.putImageData(imgData, 0, 0);
  grain.style.background = `url(${tile.toDataURL("image/png")})`;

  const syncDustSize = () => {
    dust.width = window.innerWidth;
    dust.height = window.innerHeight;
  };
  syncDustSize();
  window.addEventListener("resize", syncDustSize);

  let lastTick = -1;
  const stepFilm = () => {
    requestAnimationFrame(stepFilm);
    if (!state.filmEnabled || fx.calm) {
      dg.clearRect(0, 0, dust.width, dust.height);
      return;
    }
    const k = Math.floor(fx.now * 10);
    if (k === lastTick) return;
    lastTick = k;

    grain.style.backgroundPosition = `${Math.floor(fx.hash(k * 1.7) * 200)}px ${Math.floor(fx.hash(k * 2.9) * 200)}px`;
    const W = dust.width;
    const H = dust.height;
    dg.clearRect(0, 0, W, H);

    const count = fx.hash(k * 3.9) < 0.35 ? 1 + Math.floor(fx.hash(k * 6.1) * 2) : 0;
    dg.fillStyle = "rgba(50, 34, 20, 0.36)";
    for (let i = 0; i < count; i++) {
      const px = fx.hash(k * 2.3 + i * 7.1) * W;
      const py = fx.hash(k * 5.1 + i * 3.3) * H;
      const r = 0.7 + fx.hash(k + i * 9.7) * 1.6;
      dg.beginPath();
      dg.arc(px, py, r, 0, Math.PI * 2);
      dg.fill();
    }
  };
  requestAnimationFrame(stepFilm);
}

// ---------------------------------------------------------------------------
// 初始化与后端通信
// ---------------------------------------------------------------------------
async function initApp() {
  startDesktopHeartbeat();
  bindEvents();
  initVintageFilmOverlay();
  resizeCanvasToContainer();

  try {
    const res = await fetch("/api/init");
    if (!res.ok) throw new Error(`服务初始化异常 (${res.status})`);
    const meta = await res.json();

    for (const q of meta.qualities || []) {
      if (q.id && q.default_max_side) state.defaultMaxSides[q.id] = q.default_max_side;
    }

    els.paletteSelect.innerHTML = meta.palettes
      .map((p) => `<option value="${p.id}">${p.name} (${p.color_count}色)</option>`)
      .join("");
    els.paletteSelect.value = state.paletteId;

    els.sampleButtons.innerHTML = meta.samples
      .map(
        (s, idx) =>
          `<button type="button" class="sample-pill ${idx === 0 ? "active" : ""}" data-sample="${s.id}" title="${s.tag}">${s.name}</button>`
      )
      .join("");

    if (meta.agent) {
      applyAgentConfigMeta(meta.agent);
    }
    if (meta.wechat) {
      applyWechatStatus(meta.wechat);
    }

    if (meta.samples.length > 0) {
      await loadSample(meta.samples[0].id, true);
    }
  } catch (err) {
    showToast("初始化连接失败，请刷新窗口重试：" + err.message, true);
  }
}

// ---------------------------------------------------------------------------
// AI 智能体配置管理与对话工作流
// ---------------------------------------------------------------------------
function applyAgentConfigMeta(cfg) {
  state.agentConfig = cfg;
  const bothReady = cfg.llm_ready && cfg.tavily_ready;
  els.agentStatusDot.classList.toggle("warn", !bothReady);

  if (bothReady) {
    els.agentModelTag.textContent = `${cfg.model} · Tavily 联网已就绪`;
  } else if (cfg.llm_ready) {
    els.agentModelTag.textContent = `${cfg.model} · 待配 Tavily 搜索`;
  } else if (cfg.tavily_ready) {
    els.agentModelTag.textContent = `Tavily 已就绪 · 待配大模型`;
  } else {
    els.agentModelTag.textContent = "未配置模型与 Tavily 密钥";
  }

  if (cfg.presets && els.cfgPresetSelect.options.length === 0) {
    els.cfgPresetSelect.innerHTML = cfg.presets
      .map((p) => `<option value="${p.id}">${p.name}</option>`)
      .join("");
  }
}

function openAgentConfigDialog() {
  const cfg = state.agentConfig;
  if (!cfg) return;

  els.cfgPresetSelect.value = cfg.preset_id || "deepseek";
  els.cfgProtocolSelect.value = cfg.protocol || "openai";
  els.cfgBaseUrl.value = cfg.base_url || "";
  els.cfgModelName.value = cfg.model || "";
  els.cfgApiKey.value = "";
  els.cfgLlmSavedHint.textContent = cfg.has_api_key ? `(已保存 ${cfg.api_key_masked}，留空则保持不变)` : "";

  els.cfgTavilyKey.value = "";
  els.cfgTavilySavedHint.textContent = cfg.has_tavily_key ? `(已保存 ${cfg.tavily_api_key_masked}，留空则保持不变)` : "";
  els.cfgTavilyDepth.value = cfg.tavily_search_depth || "basic";
  els.cfgBackupImg.checked = Boolean(cfg.enable_backup_image_search);

  els.cfgProxyMode.value = cfg.proxy_mode || "system";
  els.cfgCustomProxy.value = cfg.custom_proxy || "http://127.0.0.1:7890";
  els.cfgCustomProxyField.classList.toggle("hidden", els.cfgProxyMode.value !== "custom");

  els.llmTestResult.classList.add("hidden");
  els.tavilyTestResult.classList.add("hidden");
  els.agentConfigDialog.showModal();
}

function collectDraftConfigFromForm() {
  return {
    preset_id: els.cfgPresetSelect.value,
    protocol: els.cfgProtocolSelect.value,
    base_url: els.cfgBaseUrl.value.trim(),
    model: els.cfgModelName.value.trim(),
    api_key: els.cfgApiKey.value.trim() || "****keep",
    tavily_api_key: els.cfgTavilyKey.value.trim() || "****keep",
    tavily_search_depth: els.cfgTavilyDepth.value,
    enable_backup_image_search: els.cfgBackupImg.checked,
    proxy_mode: els.cfgProxyMode.value,
    custom_proxy: els.cfgCustomProxy.value.trim(),
  };
}

async function testConnectivity(target) {
  const box = target === "tavily" ? els.tavilyTestResult : els.llmTestResult;
  const btn = target === "tavily" ? els.btnTestTavily : els.btnTestLlm;
  box.textContent = "正在发起连通性测试...";
  box.classList.remove("hidden", "error");
  btn.disabled = true;

  try {
    const draft = collectDraftConfigFromForm();
    const res = await fetch("/api/agent/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, ...draft }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "连接测试未通过");
    box.textContent = data.message;
  } catch (err) {
    box.textContent = err.message;
    box.classList.add("error");
  } finally {
    btn.disabled = false;
  }
}

async function saveAgentConfigForm(e) {
  e.preventDefault();
  try {
    const payload = collectDraftConfigFromForm();
    const res = await fetch("/api/agent/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("保存配置失败");
    const updated = await res.json();
    applyAgentConfigMeta(updated);
    els.agentConfigDialog.close();
    showToast("智能体模型与联网搜索配置已保存");
  } catch (err) {
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// 微信 ClawBot 扫码登录与桌面画布实时同步
// ---------------------------------------------------------------------------
function applyWechatStatus(st) {
  if (!st) return;
  state.wechatStatus = st;

  const isOnline = Boolean(st.connected);
  const isScanning = !isOnline && Boolean(st.login);

  els.wechatStatusDot.classList.toggle("offline", !isOnline && !isScanning);
  els.wechatStatusDot.classList.toggle("warn", isScanning);
  els.btnQuickWechat.textContent = isOnline ? "微信在线" : isScanning ? "扫码中..." : "微信扫码";

  els.wechatBotMeta.textContent = `官方 iLink 通道 · 已处理 ${st.message_count || 0} 条消息`;
  els.btnDisconnectWechat.classList.toggle("hidden", !isOnline);
  els.btnRefreshWechatQr.textContent = isOnline ? "重新扫码换绑" : "刷新二维码";

  if (isOnline) {
    els.wechatStateBadge.textContent = "已连接在线";
    els.wechatStateBadge.className = "wechat-badge online";
    els.wechatQrSection.classList.add("hidden");
    els.wechatConnectedSection.classList.remove("hidden");
    els.wechatBoundIds.textContent = st.bot_id
      ? `已绑定 ClawBot 实例：${st.bot_id}  ·  ${st.status_message || "实时监听中"}`
      : st.status_message || "微信 ClawBot 在线监听中";
  } else {
    const lStatus = st.login?.status || "";
    if (lStatus === "scaned" || lStatus === "scaned_but_redirect") {
      els.wechatStateBadge.textContent = "已扫码待确认";
      els.wechatStateBadge.className = "wechat-badge waiting";
    } else if (st.login) {
      els.wechatStateBadge.textContent = "等待微信扫码";
      els.wechatStateBadge.className = "wechat-badge waiting";
    } else {
      els.wechatStateBadge.textContent = "未连接";
      els.wechatStateBadge.className = "wechat-badge";
    }

    els.wechatConnectedSection.classList.add("hidden");
    els.wechatQrSection.classList.remove("hidden");

    if (st.login?.qr_data_url) {
      els.wechatQrImg.src = st.login.qr_data_url;
      els.wechatQrLoading.classList.add("hidden");
    } else {
      els.wechatQrLoading.classList.remove("hidden");
    }

    els.wechatLiveHint.textContent =
      st.status_message || "请使用手机微信扫描左侧二维码（需微信 8.0.70+ 开启 ClawBot 插件）";
    els.wechatVerifyWrap.classList.toggle("hidden", !st.login?.need_verify_code);
  }

  if (st.last_error) {
    els.wechatErrorBox.textContent = st.last_error;
    els.wechatErrorBox.classList.remove("hidden");
  } else {
    els.wechatErrorBox.classList.add("hidden");
  }
}

async function requestWechatLoginQr(force = false) {
  els.wechatErrorBox.classList.add("hidden");
  els.wechatConnectedSection.classList.add("hidden");
  els.wechatQrSection.classList.remove("hidden");
  els.wechatQrLoading.textContent = "正在获取微信官方二维码...";
  els.wechatQrLoading.classList.remove("hidden");
  els.btnRefreshWechatQr.disabled = true;

  try {
    const res = await fetch("/api/wechat/login_qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "获取微信登录二维码失败");
    applyWechatStatus(data);
  } catch (err) {
    els.wechatQrLoading.textContent = "获取二维码失败，请点击右上角「刷新二维码」重试";
    els.wechatErrorBox.textContent = err.message;
    els.wechatErrorBox.classList.remove("hidden");
  } finally {
    els.btnRefreshWechatQr.disabled = false;
  }
}

function openWechatDialog() {
  els.wechatClawDialog.showModal();
  if (!state.wechatStatus?.connected) {
    requestWechatLoginQr(false);
  }
  clearInterval(state.wechatPollTimer);
  state.wechatPollTimer = setInterval(async () => {
    if (!els.wechatClawDialog.open) {
      clearInterval(state.wechatPollTimer);
      return;
    }
    try {
      const res = await fetch("/api/wechat/status");
      if (res.ok) applyWechatStatus(await res.json());
    } catch (_) {}
  }, 2500);
}

function closeWechatDialog() {
  clearInterval(state.wechatPollTimer);
  els.wechatClawDialog.close();
}

async function submitWechatVerifyCode() {
  const code = els.wechatVerifyInput.value.trim();
  if (!code) return;
  els.btnSubmitVerifyCode.disabled = true;
  try {
    const res = await fetch("/api/wechat/verify_code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "提交配对码失败");
    els.wechatVerifyInput.value = "";
    applyWechatStatus(data);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    els.btnSubmitVerifyCode.disabled = false;
  }
}

async function disconnectWechatBot() {
  els.btnDisconnectWechat.disabled = true;
  try {
    const res = await fetch("/api/wechat/disconnect", { method: "POST" });
    const data = await res.json();
    applyWechatStatus(data);
    showToast("已断开微信 ClawBot 连接");
  } catch (err) {
    showToast("断开连接失败：" + err.message, true);
  } finally {
    els.btnDisconnectWechat.disabled = false;
  }
}

function handleInboundWechatSync(payload) {
  if (!payload) return;
  if (payload.user_text) {
    appendChatMessage("user", payload.user_text);
    state.chatMessages.push({ role: "user", content: payload.user_text });
  }
  if (payload.recommendations && payload.recommendations.length > 0) {
    state.recentCandidates = payload.recommendations;
  }
  if (payload.auto_apply) {
    const ap = payload.auto_apply;
    state.activeQuality = ap.active_quality || state.activeQuality;
    state.paletteId = ap.palette_id || state.paletteId;
    state.removeBg = Boolean(ap.remove_bg);
    els.paletteSelect.value = state.paletteId;
    syncRemoveBgWidgets(state.removeBg);
    els.bgTolWrap.classList.toggle("hidden", !state.removeBg);
    applyLoadedImageResult(ap, true, true);
  }
  if (payload.reply) {
    appendChatMessage("assistant", payload.reply, payload.tool_steps || [], payload.recommendations || []);
    state.chatMessages.push({ role: "assistant", content: payload.reply });
  }
  showToast("收到手机微信指令，已同步更新画布并将高清图纸发回微信");
}

function appendChatMessage(role, text, toolSteps = [], recommendations = []) {
  const wrap = document.createElement("div");
  wrap.className = `chat-msg ${role}`;

  let html = "";
  if (toolSteps && toolSteps.length > 0) {
    html += `<div class="tool-trace-list">${toolSteps
      .map((s) => `<div class="tool-trace-pill">${escapeHtml(s.label)}</div>`)
      .join("")}</div>`;
  }

  html += `<div class="chat-bubble">${escapeHtml(text)}</div>`;

  if (recommendations && recommendations.length > 0) {
    html += `<div class="rec-list">${recommendations
      .map((rec, idx) => {
        const isCurrent = rec.image_id === state.imageId;
        return `
          <div class="rec-item ${isCurrent ? "active-on-board" : ""}" data-rec-img="${escapeHtml(rec.image_id)}">
            <div class="rec-top">
              <div class="rec-thumb-pair">
                <img class="rec-bead-img" src="${rec.bead_preview_url}" alt="${escapeHtml(rec.title)} 拼豆预览" />
                <img class="rec-src-corner" src="${rec.source_thumb_url}" alt="原图参考" />
              </div>
              <div class="rec-meta">
                <div class="rec-title" title="${escapeHtml(rec.title)}">方案 ${idx + 1} · ${escapeHtml(rec.title)}</div>
                <div class="rec-specs num">${escapeHtml(rec.quality_name)} (${rec.grid_width}×${rec.grid_height}) · ${rec.total_beads.toLocaleString()} 颗 · ${rec.unique_colors} 色</div>
                <div class="rec-time num">预估时长：约 ${escapeHtml(rec.estimated_time)}</div>
              </div>
            </div>
            <div class="rec-actions">
              <button type="button" class="btn btn-primary rec-apply-btn" data-apply-rec="${escapeHtml(rec.image_id)}" data-rec-q="${escapeHtml(rec.quality)}" data-rec-pal="${escapeHtml(rec.palette_id)}" data-rec-bg="${rec.remove_bg ? "1" : "0"}">
                ${isCurrent ? "当前已在画布" : "加载到画布"}
              </button>
              <button type="button" class="text-action-btn" data-tune-rec="${escapeHtml(rec.image_id)}" data-rec-q="${escapeHtml(rec.quality)}" data-rec-pal="${escapeHtml(rec.palette_id)}" data-rec-bg="${rec.remove_bg ? "1" : "0"}">
                三档微调
              </button>
            </div>
          </div>
        `;
      })
      .join("")}</div>`;
  }

  wrap.innerHTML = html;
  els.chatHistory.appendChild(wrap);
  els.chatHistory.scrollTop = els.chatHistory.scrollHeight;
}

function updateActiveRecCardHighlight() {
  els.chatHistory.querySelectorAll(".rec-item").forEach((el) => {
    const isAct = el.dataset.recImg === state.imageId;
    el.classList.toggle("active-on-board", isAct);
    const btn = el.querySelector("[data-apply-rec]");
    if (btn) btn.textContent = isAct ? "当前已在画布" : "加载到画布";
  });
}

async function sendAgentChatPrompt(promptText) {
  const clean = promptText.trim();
  if (!clean || state.agentBusy) return;

  state.agentBusy = true;
  els.btnSendPrompt.disabled = true;
  if (els.hoseSendBtn) els.hoseSendBtn.disabled = true;
  els.agentPromptInput.value = "";
  appendChatMessage("user", clean);
  state.chatMessages.push({ role: "user", content: clean });

  const pendingEl = document.createElement("div");
  pendingEl.className = "chat-msg assistant";
  pendingEl.innerHTML = `<div class="tool-trace-pill">正在理解需求、执行联网检索并测算拼豆图纸...</div>`;
  els.chatHistory.appendChild(pendingEl);
  els.chatHistory.scrollTop = els.chatHistory.scrollHeight;
  setLoading(true);

  try {
    const res = await fetch("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: state.chatMessages.slice(-8),
        canvas_context: {
          image_id: state.imageId,
          quality: state.activeQuality,
          palette_id: state.paletteId,
          remove_bg: state.removeBg,
        },
        recent_candidates: state.recentCandidates,
      }),
    });
    const data = await res.json();
    pendingEl.remove();

    if (!res.ok) throw new Error(data.error || "智能体请求失败");

    if (data.auto_apply) {
      const ap = data.auto_apply;
      state.activeQuality = ap.active_quality || state.activeQuality;
      state.paletteId = ap.palette_id || state.paletteId;
      state.removeBg = Boolean(ap.remove_bg);
      els.paletteSelect.value = state.paletteId;
      syncRemoveBgWidgets(state.removeBg);
      els.bgTolWrap.classList.toggle("hidden", !state.removeBg);
      applyLoadedImageResult(ap, true, true);
    }

    if (data.recommendations && data.recommendations.length > 0) {
      state.recentCandidates = data.recommendations;
    }

    appendChatMessage("assistant", data.reply, data.tool_steps || [], data.recommendations || []);
    state.chatMessages.push({ role: "assistant", content: data.reply });

    if (data.needs_config) {
      openAgentConfigDialog();
    }
  } catch (err) {
    pendingEl.remove();
    appendChatMessage("assistant", `请求遇到问题：${err.message}`);
  } finally {
    state.agentBusy = false;
    els.btnSendPrompt.disabled = false;
    if (els.hoseSendBtn) els.hoseSendBtn.disabled = false;
    setLoading(false);
  }
}

async function applyRecommendedCandidate(imgId, quality, paletteId, removeBg, jumpToManual = false) {
  setLoading(true);
  try {
    const res = await fetch("/api/agent/apply_candidate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_id: imgId,
        quality,
        palette_id: paletteId,
        remove_bg: removeBg,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载候选方案失败");

    state.activeQuality = data.active_quality || quality;
    state.paletteId = data.palette_id || paletteId;
    state.removeBg = Boolean(data.remove_bg);
    els.paletteSelect.value = state.paletteId;
    syncRemoveBgWidgets(state.removeBg);
    els.bgTolWrap.classList.toggle("hidden", !state.removeBg);

    applyLoadedImageResult(data, true, true);
    updateActiveRecCardHighlight();
    if (jumpToManual) {
      switchLeftMode("manual");
    }
    showToast("已将该推荐拼豆方案加载至中央画布");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------------
// 常规原图加载与重算逻辑
// ---------------------------------------------------------------------------
async function loadSample(sampleId, quietBoot = false) {
  setLoading(true);
  try {
    const res = await fetch("/api/load_sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sample_id: sampleId,
        palette_id: state.paletteId,
        remove_bg: state.removeBg,
        bg_tolerance: state.bgTolerance,
      }),
    });
    if (!res.ok) throw new Error(`加载示例返回错误 (${res.status})`);
    const data = await res.json();
    applyLoadedImageResult(data, true, !quietBoot);
  } catch (err) {
    showToast("加载示例失败：" + err.message, true);
  } finally {
    setLoading(false);
  }
}

async function uploadImageFile(file) {
  if (!file) return;
  if (!confirmDiscardManualEdits("导入新图片")) return;

  document.querySelectorAll(".sample-pill").forEach((b) => b.classList.remove("active"));
  setLoading(true);
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("palette_id", state.paletteId);
    fd.append("remove_bg", state.removeBg ? "1" : "0");
    fd.append("bg_tolerance", String(state.bgTolerance));

    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "不支持该图片格式，请选择 PNG/JPG/WEBP 文件");
    applyLoadedImageResult(data, true, true);
    switchLeftMode("manual");
    showToast("已生成简略、高清、还原三档拼豆图纸");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setLoading(false);
  }
}

async function recomputeAllTiers(customMaxSide = null) {
  if (!state.imageId) return;
  setLoading(true);
  try {
    const res = await fetch("/api/recompute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_id: state.imageId,
        palette_id: state.paletteId,
        remove_bg: state.removeBg,
        bg_tolerance: state.bgTolerance,
        only_quality: customMaxSide !== null ? state.activeQuality : null,
        custom_max_side: customMaxSide,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "重算失败");

    if (data.tiers) {
      Object.assign(state.tiers, data.tiers);
      for (const q of Object.keys(data.tiers)) {
        state.undoStacks[q] = [];
        state.redoStacks[q] = [];
        state.manualEditsByTier[q] = false;
      }
    }
    state.spotlightColorIdx = null;
    refreshAllUI(customMaxSide === null, true);
  } catch (err) {
    showToast("重新生成失败：" + err.message, true);
  } finally {
    setLoading(false);
  }
}

function applyLoadedImageResult(data, fitView = true, cheerMascot = false) {
  state.imageId = data.image_id;
  state.tiers = data.tiers;
  state.spotlightColorIdx = null;
  state.undoStacks = { simple: [], hd: [], faithful: [] };
  state.redoStacks = { simple: [], hd: [], faithful: [] };
  state.manualEditsByTier = { simple: false, hd: false, faithful: false };
  restoreCompletedProgress(data.image_id);

  els.sourceThumb.src = data.source_data_url;
  els.imgDimBadge.textContent = `${data.source_width}×${data.source_height}px`;

  const img = new Image();
  img.onload = () => {
    state.sourceImgObj = img;
    requestRender();
  };
  img.src = data.source_data_url;

  const pat = currentPattern();
  if (pat && pat.bom.length > 0) {
    state.selectedColorIdx = pat.bom[0].palette_index;
  }

  updateActiveRecCardHighlight();
  refreshAllUI(fitView, cheerMascot);
}

// ---------------------------------------------------------------------------
// UI 状态同步更新
// ---------------------------------------------------------------------------
function refreshAllUI(fitAfter = false, cheerMascot = false) {
  updateQualityCards();
  const pat = currentPattern();
  if (!pat) return;

  const maxDim = Math.max(pat.grid_width, pat.grid_height);
  syncSizeSliderWidgets(maxDim);

  const defDim = state.defaultMaxSides[state.activeQuality] || 58;
  els.customModifiedTag.classList.toggle("hidden", maxDim === defDim);

  document.querySelectorAll(".tier-card").forEach((card) => {
    const isAct = card.dataset.quality === state.activeQuality;
    card.classList.toggle("active", isAct);
    card.setAttribute("aria-checked", isAct ? "true" : "false");
  });

  document.querySelectorAll(".quick-tier-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.qtier === state.activeQuality);
  });

  updateBrushColorChip(pat, cheerMascot);
  updateHistoryButtons();
  updateRightDashboard(pat);
  renderBomList(pat);
  renderFullPaletteGrid(pat);
  updateSpotlightBanner(pat);

  els.boardSummaryTag.textContent = `${pat.quality_name} · ${pat.grid_width}×${pat.grid_height} 格 · ${pat.total_beads.toLocaleString()} 颗`;

  if (fitAfter) {
    fitPatternToViewport();
  } else {
    requestRender();
  }
}

function updateQualityCards() {
  for (const q of ["simple", "hd", "faithful"]) {
    const t = state.tiers[q];
    if (!t) continue;
    const prof = t.time_estimate.profiles[state.skillLevel] || t.time_estimate.profiles.standard;
    const timeEl = document.getElementById(`tierTime_${q}`);
    const statsEl = document.getElementById(`tierStats_${q}`);
    if (timeEl) timeEl.textContent = `约 ${prof.formatted}`;
    if (statsEl) {
      statsEl.textContent = `${t.total_beads.toLocaleString()} 颗豆 · ${t.unique_colors} 色 (${t.grid_width}×${t.grid_height})`;
    }
  }
}

function updateBrushColorChip(pat, cheer = false) {
  const cinfo = pat.palette_lookup[String(state.selectedColorIdx)] || Object.values(pat.palette_lookup)[0];
  if (!cinfo) return;
  els.brushSwatchDot.style.background = cinfo.hex;
  els.brushColorCode.textContent = `${cinfo.code} ${cinfo.name}`;

  // 同步更新橡皮管拼豆小精灵的豆子颜色与肚子色号铭牌
  if (els.hoseBeadMascot && typeof els.hoseBeadMascot.setBead === "function") {
    els.hoseBeadMascot.setBead(cinfo.hex, cinfo.code, cinfo.text_color, cheer);
  }
}

function renderFullPaletteGrid(pat) {
  const entries = Object.entries(pat.palette_lookup);
  const kw = state.paletteSearch?.trim().toLowerCase() || "";
  const filtered = kw
    ? entries.filter(([, c]) => c.code.toLowerCase().includes(kw) || c.name.toLowerCase().includes(kw))
    : entries;

  els.fullPaletteGrid.innerHTML = filtered
    .map(([idxStr, c]) => {
      const idx = parseInt(idxStr, 10);
      const sel = idx === state.selectedColorIdx ? "selected" : "";
      return `<button type="button" class="pal-cell-btn num ${sel}" data-palidx="${idx}" style="background:${c.hex};color:${c.text_color}" title="${c.code} ${c.name} (${c.hex})">${c.code}</button>`;
    })
    .join("");
}

function updateHistoryButtons() {
  const uStack = state.undoStacks[state.activeQuality] || [];
  const rStack = state.redoStacks[state.activeQuality] || [];
  els.btnUndo.disabled = uStack.length === 0;
  els.btnRedo.disabled = rStack.length === 0;
}

function updateRightDashboard(pat) {
  const est = pat.time_estimate;
  const prof = est.profiles[state.skillLevel] || est.profiles.standard;

  els.heroDuration.textContent = prof.formatted;
  els.diffBadge.textContent = `${est.difficulty.label} (${est.difficulty.score}/5)`;

  els.metricTotalBeads.textContent = `${pat.total_beads.toLocaleString()} 颗`;
  els.metricUniqueColors.textContent = `${pat.unique_colors} 种`;
  els.metricBoards.textContent = `${est.boards_29.cols}×${est.boards_29.rows} (${est.boards_29.total}块)`;

  const sz = pat.physical_size_cm[state.beadSpec];
  els.metricPhysSize.textContent = `${sz.width} × ${sz.height} cm`;
  els.speedHint.textContent = `净摆豆约 ${prof.speed_beads_per_min} 颗/分`;
  els.scatterHint.textContent = `散点率 ${est.spatial_stats.scattered_ratio}%`;

  const bm = prof.breakdown_minutes;
  const sumM = Math.max(1, bm.prep + bm.placing + bm.detail + bm.ironing);
  els.barPrep.style.width = `${(bm.prep / sumM) * 100}%`;
  els.barPlace.style.width = `${(bm.placing / sumM) * 100}%`;
  els.barDetail.style.width = `${(bm.detail / sumM) * 100}%`;
  els.barIron.style.width = `${(bm.ironing / sumM) * 100}%`;

  els.minPrep.textContent = `${bm.prep}m`;
  els.minPlace.textContent = `${bm.placing}m`;
  els.minDetail.textContent = `${bm.detail}m`;
  els.minIron.textContent = `${bm.ironing}m`;

  els.sessionAdvice.textContent = est.session_advice;
  els.bomCountTag.textContent = `${pat.unique_colors} 色`;
  updateProgressStrip(pat, prof);
}

function updateProgressStrip(pat, prof) {
  const doneSet = activeCompletedSet();
  let doneBeads = 0;
  for (const item of pat.bom) {
    if (doneSet.has(item.palette_index)) {
      doneBeads += item.count;
    }
  }
  if (doneBeads === 0) {
    els.progressStrip.classList.add("hidden");
    return;
  }
  els.progressStrip.classList.remove("hidden");
  const ratioLeft = Math.max(0, 1 - doneBeads / Math.max(1, pat.total_beads));
  const remMin = Math.max(1, Math.round(prof.total_minutes * ratioLeft));
  const remTxt = remMin >= 60 ? `${Math.floor(remMin / 60)}小时${remMin % 60}分` : `${remMin}分钟`;
  els.progressText.textContent = `已拼完 ${doneBeads.toLocaleString()} / ${pat.total_beads.toLocaleString()} 颗`;
  els.remainingTimeText.textContent = doneBeads >= pat.total_beads ? "全部色号摆豆已完成!" : `剩余约 ${remTxt}`;
}

function renderBomList(pat) {
  const doneSet = activeCompletedSet();
  const kw = state.bomFilter.trim().toLowerCase();
  let items = pat.bom.slice();

  if (kw) {
    items = items.filter(
      (it) => it.code.toLowerCase().includes(kw) || it.name.toLowerCase().includes(kw)
    );
  }

  items.sort((a, b) => {
    const aDone = doneSet.has(a.palette_index) ? 1 : 0;
    const bDone = doneSet.has(b.palette_index) ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;
    if (state.bomSort === "code") return a.code.localeCompare(b.code, "zh-CN");
    return b.count - a.count;
  });

  const targetSvg = `<svg class="ui-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.2"/><circle cx="8" cy="8" r="1.8"/><path d="M8 1.2v1.6M8 13.2v1.6M1.2 8h1.6M13.2 8h1.6"/></svg>`;

  els.bomList.innerHTML = items
    .map((item) => {
      const isSpot = state.spotlightColorIdx === item.palette_index;
      const isBrush = state.selectedColorIdx === item.palette_index;
      const isDone = doneSet.has(item.palette_index);
      return `
        <div class="bom-row ${isSpot ? "spotlight" : ""} ${isBrush ? "brush-selected" : ""} ${isDone ? "done" : ""}">
          <label class="bom-check-wrap" title="标记 ${item.code} ${item.name} 已拼完">
            <input type="checkbox" class="bom-check" data-check="${item.palette_index}" aria-label="标记 ${item.code} ${item.name} 已拼完" ${isDone ? "checked" : ""} />
          </label>
          <button type="button" class="bom-main-btn" data-select="${item.palette_index}" title="点击将 ${item.code} ${item.name} 设为改色笔颜色">
            <span class="bom-swatch num" style="background:${item.hex};color:${item.text_color}">${item.code}</span>
            <span class="bom-info">
              <span class="bom-name">${item.name}</span>
              <span class="bom-pct num">${item.percentage}%</span>
            </span>
            <span class="bom-count num">${item.count} 颗</span>
          </button>
          <button type="button" class="bom-spot-btn" data-spot="${item.palette_index}" aria-pressed="${isSpot}" aria-label="单色高亮定位 ${item.code} ${item.name}" title="在画布中单色聚光灯高亮 ${item.code}">
            ${targetSvg}
          </button>
        </div>
      `;
    })
    .join("");
}

function updateSpotlightBanner(pat) {
  if (state.spotlightColorIdx === null) {
    els.spotlightBanner.classList.add("hidden");
    return;
  }
  const cinfo = pat.palette_lookup[String(state.spotlightColorIdx)];
  if (!cinfo) {
    els.spotlightBanner.classList.add("hidden");
    return;
  }
  const bomItem = pat.bom.find((b) => b.palette_index === state.spotlightColorIdx);
  const cnt = bomItem ? bomItem.count : 0;
  els.spotlightSwatch.style.background = cinfo.hex;
  els.spotlightText.textContent = `单色聚光灯跟拼：${cinfo.code} ${cinfo.name}（共 ${cnt} 颗）`;
  els.spotlightBanner.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Canvas 1930s 赛璐璐手绘感拼豆渲染引擎
// ---------------------------------------------------------------------------
let renderPending = false;
function requestRender() {
  if (!renderPending) {
    renderPending = true;
    requestAnimationFrame(() => {
      renderPending = false;
      drawScene();
    });
  }
}

function resizeCanvasToContainer() {
  const rect = els.canvasViewport.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  els.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  els.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  requestRender();
}

function fitPatternToViewport() {
  const pat = currentPattern();
  if (!pat) return;
  const rect = els.canvasViewport.getBoundingClientRect();
  const margin = state.showRuler ? 76 : 40;
  const availW = Math.max(120, rect.width - margin);
  const availH = Math.max(120, rect.height - margin);

  const effGridW = state.viewMode === "compare" ? pat.grid_width * 2 + 3 : pat.grid_width;
  const cellPx = Math.min(availW / effGridW, availH / pat.grid_height);
  state.baseCellPx = 20;
  state.zoom = Math.max(0.18, Math.min(4.2, cellPx / state.baseCellPx));

  const totalW = effGridW * state.baseCellPx * state.zoom;
  const totalH = pat.grid_height * state.baseCellPx * state.zoom;
  state.panX = (rect.width - totalW) / 2;
  state.panY = (rect.height - totalH) / 2 + (state.showRuler ? 8 : 0);

  els.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  requestRender();
}

function drawScene() {
  const rect = els.canvasViewport.getBoundingClientRect();
  const vw = rect.width;
  const vh = rect.height;
  ctx.clearRect(0, 0, vw, vh);

  const pat = currentPattern();
  if (!pat) return;

  const cell = state.baseCellPx * state.zoom;
  const gw = pat.grid_width;
  const gh = pat.grid_height;
  const boardW = gw * cell;
  const boardH = gh * cell;

  const isDaylight = state.daylightMat;
  const boardBg = isDaylight ? "#fff9eb" : "#251d16";
  const pegHoleFill = isDaylight ? "#e8d7b4" : "#18120d";
  const emptyPinFill = isDaylight ? "rgba(92, 71, 48, 0.28)" : "rgba(251, 231, 192, 0.22)";

  let ox = state.panX;
  const oy = state.panY;

  if (state.viewMode === "compare" && state.sourceImgObj) {
    ctx.save();
    ctx.fillStyle = boardBg;
    ctx.strokeStyle = "#251d16";
    ctx.lineWidth = 3;
    ctx.fillRect(ox - 2, oy - 2, boardW + 4, boardH + 4);
    ctx.strokeRect(ox - 2, oy - 2, boardW + 4, boardH + 4);
    ctx.drawImage(state.sourceImgObj, ox, oy, boardW, boardH);
    ctx.fillStyle = "#fbe7c0";
    ctx.fillRect(ox + 8, oy + 8, 78, 24);
    ctx.strokeRect(ox + 8, oy + 8, 78, 24);
    ctx.fillStyle = "#251d16";
    ctx.font = "700 12px 'Microsoft YaHei UI', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("原始图片", ox + 47, oy + 20);
    ctx.restore();
    ox = state.panX + boardW + cell * 3;
  }

  // 1930s 赛璐璐手绘定位拼板底框（硬边墨水投影 + 浓墨描边）
  ctx.save();
  ctx.fillStyle = "rgba(37, 29, 22, 0.24)";
  ctx.fillRect(ox + 5, oy + 6, boardW, boardH);
  ctx.fillStyle = boardBg;
  ctx.fillRect(ox, oy, boardW, boardH);
  ctx.strokeStyle = "#251d16";
  ctx.lineWidth = 2.6;
  ctx.strokeRect(ox - 1, oy - 1, boardW + 2, boardH + 2);
  ctx.restore();

  const grid = pat.grid;
  const lookup = pat.palette_lookup;
  const hasSpotlight = state.spotlightColorIdx !== null;

  const cStart = Math.max(0, Math.floor((0 - ox) / cell));
  const cEnd = Math.min(gw, Math.ceil((vw - ox) / cell));
  const rStart = Math.max(0, Math.floor((0 - oy) / cell));
  const rEnd = Math.min(gh, Math.ceil((vh - oy) / cell));

  const showCodeText =
    state.viewMode === "code" || (hasSpotlight && cell >= 14) || (state.viewMode !== "ring" && cell >= 28);

  if (showCodeText) {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `700 ${Math.max(8, Math.floor(cell * 0.39))}px "Hose Hand", "Microsoft YaHei UI", sans-serif`;
  }

  for (let r = rStart; r < rEnd; r++) {
    const y0 = oy + r * cell;
    const row = grid[r];
    for (let c = cStart; c < cEnd; c++) {
      const x0 = ox + c * cell;
      const val = row[c];

      if (val < 0) {
        if (cell >= 7) {
          ctx.fillStyle = emptyPinFill;
          ctx.beginPath();
          ctx.arc(x0 + cell * 0.5, y0 + cell * 0.5, Math.max(1.2, cell * 0.1), 0, Math.PI * 2);
          ctx.fill();
        }
        continue;
      }

      const cinfo = lookup[String(val)];
      if (!cinfo) continue;

      const dimmed = hasSpotlight && val !== state.spotlightColorIdx;
      ctx.globalAlpha = dimmed ? 0.14 : 1.0;

      if (state.viewMode === "ring") {
        const cx = x0 + cell * 0.5;
        const cy = y0 + cell * 0.5;
        const outerR = cell * 0.46;
        const innerR = cell * 0.185;

        ctx.fillStyle = cinfo.hex;
        ctx.beginPath();
        ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
        ctx.fill();

        // 赛璐璐微墨线外圈，保证浅色豆在羊皮纸底板上同样饱满清晰
        if (cell >= 7) {
          ctx.strokeStyle = isDaylight ? "rgba(37, 29, 22, 0.42)" : "rgba(0, 0, 0, 0.36)";
          ctx.lineWidth = Math.max(0.8, cell * 0.048);
          ctx.stroke();
        }

        if (cell >= 8) {
          ctx.strokeStyle = "rgba(255, 252, 240, 0.36)";
          ctx.lineWidth = Math.max(1, cell * 0.065);
          ctx.beginPath();
          ctx.arc(cx, cy, outerR * 0.75, Math.PI * 1.1, Math.PI * 1.72);
          ctx.stroke();

          ctx.fillStyle = pegHoleFill;
          ctx.beginPath();
          ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
          ctx.fill();
        }

        if (hasSpotlight && !dimmed && cell >= 16) {
          ctx.fillStyle = cinfo.text_color;
          ctx.fillText(cinfo.code, cx, cy);
        }
      } else {
        const pad = state.viewMode === "flat" ? 0 : 0.45;
        ctx.fillStyle = cinfo.hex;
        ctx.fillRect(x0 + pad, y0 + pad, cell - pad * 2, cell - pad * 2);

        if (showCodeText && cell >= 13 && (!hasSpotlight || !dimmed)) {
          ctx.fillStyle = cinfo.text_color;
          ctx.fillText(cinfo.code, x0 + cell * 0.5, y0 + cell * 0.52);
        }
      }
    }
  }
  ctx.globalAlpha = 1.0;

  if (cell >= 10 || state.viewMode === "code") {
    ctx.lineWidth = 1;
    const majorGrid = isDaylight ? "rgba(37, 29, 22, 0.34)" : "rgba(251, 231, 192, 0.32)";
    const minorGrid = isDaylight ? "rgba(37, 29, 22, 0.14)" : "rgba(251, 231, 192, 0.13)";

    for (let c = cStart; c <= cEnd; c++) {
      if (c % 5 === 0) ctx.strokeStyle = majorGrid;
      else if (state.viewMode === "code" && cell >= 12) ctx.strokeStyle = minorGrid;
      else continue;
      const x = Math.round(ox + c * cell) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, oy);
      ctx.lineTo(x, oy + boardH);
      ctx.stroke();
    }
    for (let r = rStart; r <= rEnd; r++) {
      if (r % 5 === 0) ctx.strokeStyle = majorGrid;
      else if (state.viewMode === "code" && cell >= 12) ctx.strokeStyle = minorGrid;
      else continue;
      const y = Math.round(oy + r * cell) + 0.5;
      ctx.beginPath();
      ctx.moveTo(ox, y);
      ctx.lineTo(ox + boardW, y);
      ctx.stroke();
    }
  }

  if (state.showBoard29) {
    ctx.strokeStyle = isDaylight ? "rgba(185, 43, 22, 0.88)" : "rgba(248, 113, 113, 0.9)";
    ctx.lineWidth = 2.2;
    ctx.setLineDash([6, 4]);
    for (let c = 29; c < gw; c += 29) {
      const x = ox + c * cell;
      ctx.beginPath();
      ctx.moveTo(x, oy);
      ctx.lineTo(x, oy + boardH);
      ctx.stroke();
    }
    for (let r = 29; r < gh; r += 29) {
      const y = oy + r * cell;
      ctx.beginPath();
      ctx.moveTo(ox, y);
      ctx.lineTo(ox + boardW, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  if (state.showRuler && cell >= 9) {
    const rulerNormal = isDaylight ? "#3b2c1e" : "#fbe7c0";
    const ruler29 = isDaylight ? "#b92b16" : "#fca5a5";
    ctx.font = `700 ${Math.min(13, Math.max(10, Math.floor(cell * 0.52)))}px "Hose Hand", "Segoe UI", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    const step = cell < 15 ? 5 : 1;
    for (let c = cStart; c < cEnd; c++) {
      if ((c + 1) % step === 0 || c === 0) {
        ctx.fillStyle = (c + 1) % 29 === 0 ? ruler29 : rulerNormal;
        ctx.fillText(String(c + 1), ox + c * cell + cell * 0.5, oy - 5);
      }
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let r = rStart; r < rEnd; r++) {
      if ((r + 1) % step === 0 || r === 0) {
        ctx.fillStyle = (r + 1) % 29 === 0 ? ruler29 : rulerNormal;
        ctx.fillText(String(r + 1), ox - 6, oy + r * cell + cell * 0.5);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 坐标转换、手工改色与撤销/重做栈
// ---------------------------------------------------------------------------
function screenToGrid(clientX, clientY) {
  const pat = currentPattern();
  if (!pat) return null;
  const rect = els.canvasViewport.getBoundingClientRect();
  const mx = clientX - rect.left;
  const my = clientY - rect.top;
  const cell = state.baseCellPx * state.zoom;
  const boardW = pat.grid_width * cell;
  const ox = state.viewMode === "compare" && state.sourceImgObj ? state.panX + boardW + cell * 3 : state.panX;
  const oy = state.panY;

  const col = Math.floor((mx - ox) / cell);
  const row = Math.floor((my - oy) / cell);
  if (col < 0 || col >= pat.grid_width || row < 0 || row >= pat.grid_height) return null;
  return { row, col };
}

function applyToolAtCell(row, col) {
  const pat = currentPattern();
  if (!pat) return;
  const curVal = pat.grid[row][col];

  if (state.activeTool === "picker") {
    if (curVal >= 0) {
      state.selectedColorIdx = curVal;
      updateBrushColorChip(pat, true);
      renderBomList(pat);
      renderFullPaletteGrid(pat);
      const cinfo = pat.palette_lookup[String(curVal)];
      showToast(`已吸取色号：${cinfo.code} ${cinfo.name}`);
      setTool("brush");
    }
    return;
  }

  const targetVal = state.activeTool === "eraser" ? -1 : state.selectedColorIdx;
  if (curVal === targetVal) return;

  if (!state.strokeSnapshot) {
    state.strokeSnapshot = cloneGrid(pat.grid);
  }

  pat.grid[row][col] = targetVal;
  state.dirtyStroke = true;
  state.manualEditsByTier[state.activeQuality] = true;
  requestRender();
}

async function commitStrokeAndReestimate() {
  if (!state.dirtyStroke) {
    state.strokeSnapshot = null;
    return;
  }
  state.dirtyStroke = false;
  if (state.strokeSnapshot) {
    const uStack = state.undoStacks[state.activeQuality];
    uStack.push(state.strokeSnapshot);
    if (uStack.length > 30) uStack.shift();
    state.redoStacks[state.activeQuality] = [];
    state.strokeSnapshot = null;
    updateHistoryButtons();
  }
  if (els.hoseBeadMascot && typeof els.hoseBeadMascot.bop === "function") {
    els.hoseBeadMascot.bop("好手艺！豆子数量和工时已实时重算！");
  }
  await syncGridStatsFromServer();
}

async function undoEdit() {
  const pat = currentPattern();
  const uStack = state.undoStacks[state.activeQuality];
  if (!pat || !uStack || uStack.length === 0) return;

  state.redoStacks[state.activeQuality].push(cloneGrid(pat.grid));
  pat.grid = uStack.pop();
  updateHistoryButtons();
  requestRender();
  await syncGridStatsFromServer();
}

async function redoEdit() {
  const pat = currentPattern();
  const rStack = state.redoStacks[state.activeQuality];
  if (!pat || !rStack || rStack.length === 0) return;

  state.undoStacks[state.activeQuality].push(cloneGrid(pat.grid));
  pat.grid = rStack.pop();
  updateHistoryButtons();
  requestRender();
  await syncGridStatsFromServer();
}

async function syncGridStatsFromServer() {
  const pat = currentPattern();
  if (!pat) return;
  try {
    const res = await fetch("/api/reestimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        grid: pat.grid,
        palette_id: pat.palette_id,
      }),
    });
    if (!res.ok) throw new Error("工时同步失败");
    const updated = await res.json();
    pat.total_beads = updated.total_beads;
    pat.unique_colors = updated.unique_colors;
    pat.bom = updated.bom;
    pat.physical_size_cm = updated.physical_size_cm;
    pat.time_estimate = updated.time_estimate;
    refreshAllUI(false, false);
  } catch (err) {
    showToast("统计更新异常：" + err.message, true);
  }
}

function setTool(toolName) {
  state.activeTool = toolName;
  document.querySelectorAll(".tool-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tool === toolName);
  });
  updateViewportCursor();
}

function updateViewportCursor() {
  const panMode = state.activeTool === "pan" || state.spacePressed;
  els.canvasViewport.classList.toggle("crosshair", !panMode && !state.isDragging);
}

// ---------------------------------------------------------------------------
// 事件绑定（包含全套 Rubber Hose 自定义元素事件监听）
// ---------------------------------------------------------------------------
function bindEvents() {
  window.addEventListener("resize", resizeCanvasToContainer);

  // 1930s 复古胶片颗粒叠层开关
  els.btnFilmMode.addEventListener("click", () => {
    state.filmEnabled = !state.filmEnabled;
    els.filmOverlay.classList.toggle("hidden", !state.filmEnabled);
    els.btnFilmMode.setAttribute("aria-pressed", String(state.filmEnabled));
    els.filmModeLabel.textContent = state.filmEnabled ? "胶片开" : "胶片关";
  });

  // 官方 <hose-tabs> 文件夹踢腿标签切换事件
  if (els.hoseLeftTabs) {
    els.hoseLeftTabs.addEventListener("change", (e) => {
      if (e.detail?.value) {
        switchLeftMode(e.detail.value);
      }
    });
  }
  document.querySelectorAll(".left-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchLeftMode(tab.dataset.leftmode));
  });

  // 专属 <hose-bead-mascot> 台词联动显示
  if (els.hoseBeadMascot) {
    els.hoseBeadMascot.addEventListener("hose:line", (e) => {
      if (e.detail?.text && els.mascotSpeech) {
        els.mascotSpeech.textContent = e.detail.text;
      }
    });
  }

  // 打开与关闭微信 ClawBot 扫码连接窗口
  els.btnOpenWechatBot.addEventListener("click", openWechatDialog);
  els.btnQuickWechat.addEventListener("click", openWechatDialog);
  els.btnCloseWechatIcon.addEventListener("click", closeWechatDialog);
  els.btnCloseWechatFooter.addEventListener("click", closeWechatDialog);
  els.wechatClawDialog.addEventListener("close", () => clearInterval(state.wechatPollTimer));
  els.btnRefreshWechatQr.addEventListener("click", () => requestWechatLoginQr(true));
  els.btnDisconnectWechat.addEventListener("click", disconnectWechatBot);
  els.btnSubmitVerifyCode.addEventListener("click", submitWechatVerifyCode);
  els.wechatVerifyInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitWechatVerifyCode();
    }
  });

  // 打开与关闭大模型/Tavily配置窗口
  els.btnOpenAgentConfig.addEventListener("click", openAgentConfigDialog);
  els.btnQuickConfig.addEventListener("click", openAgentConfigDialog);
  els.btnCloseConfigIcon.addEventListener("click", () => els.agentConfigDialog.close());
  els.btnCancelConfig.addEventListener("click", () => els.agentConfigDialog.close());

  els.cfgPresetSelect.addEventListener("change", () => {
    const presets = state.agentConfig?.presets || [];
    const found = presets.find((p) => p.id === els.cfgPresetSelect.value);
    if (found) {
      els.cfgProtocolSelect.value = found.protocol;
      els.cfgBaseUrl.value = found.base_url;
      els.cfgModelName.value = found.default_model;
    }
  });
  els.cfgProxyMode.addEventListener("change", () => {
    els.cfgCustomProxyField.classList.toggle("hidden", els.cfgProxyMode.value !== "custom");
  });
  els.btnTestLlm.addEventListener("click", () => testConnectivity("llm"));
  els.btnTestTavily.addEventListener("click", () => testConnectivity("tavily"));
  els.agentConfigForm.addEventListener("submit", saveAgentConfigForm);

  // 对话发送（同时支持拍击 <hose-button> 红圆顶角色、点击发送按钮或按 Enter）
  els.agentChatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendAgentChatPrompt(els.agentPromptInput.value);
  });
  if (els.hoseSendBtn) {
    els.hoseSendBtn.addEventListener("click", () => {
      if (!els.agentPromptInput.value.trim()) {
        showToast("请先在上方输入框写下想要的拼豆图案描述再拍红钮哟！");
      }
    });
  }
  els.agentPromptInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendAgentChatPrompt(els.agentPromptInput.value);
    }
  });

  els.chatHistory.addEventListener("click", (e) => {
    const starter = e.target.closest(".starter-chip");
    if (starter) {
      sendAgentChatPrompt(starter.dataset.prompt);
      return;
    }

    const applyBtn = e.target.closest("[data-apply-rec]");
    if (applyBtn) {
      applyRecommendedCandidate(
        applyBtn.dataset.applyRec,
        applyBtn.dataset.recQ,
        applyBtn.dataset.recPal,
        applyBtn.dataset.recBg === "1",
        false
      );
      return;
    }

    const tuneBtn = e.target.closest("[data-tune-rec]");
    if (tuneBtn) {
      if (tuneBtn.dataset.tuneRec === state.imageId) {
        switchLeftMode("manual");
      } else {
        applyRecommendedCandidate(
          tuneBtn.dataset.tuneRec,
          tuneBtn.dataset.recQ,
          tuneBtn.dataset.recPal,
          tuneBtn.dataset.recBg === "1",
          true
        );
      }
    }
  });

  // 专注跟拼模式
  els.btnCraftFocus.addEventListener("click", () => {
    state.craftFocus = !state.craftFocus;
    els.workspaceGrid.classList.toggle("craft-focus", state.craftFocus);
    els.btnCraftFocus.setAttribute("aria-pressed", String(state.craftFocus));
    els.craftFocusLabel.textContent = state.craftFocus ? "展开左栏" : "专注跟拼";
    resizeCanvasToContainer();
    fitPatternToViewport();
  });

  // 上传与键盘无障碍支持
  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      els.fileInput.click();
    }
  });
  els.fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) uploadImageFile(e.target.files[0]);
    e.target.value = "";
  });

  els.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropzone.classList.add("dragover");
  });
  els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
  els.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    els.dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadImageFile(e.dataTransfer.files[0]);
    }
  });

  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadImageFile(e.dataTransfer.files[0]);
    }
  });
  window.addEventListener("paste", (e) => {
    if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
    const items = e.clipboardData?.items || [];
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        uploadImageFile(item.getAsFile());
        break;
      }
    }
  });

  els.sampleButtons.addEventListener("click", (e) => {
    const btn = e.target.closest(".sample-pill");
    if (!btn) return;
    if (!confirmDiscardManualEdits("切换示例图案")) return;
    document.querySelectorAll(".sample-pill").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadSample(btn.dataset.sample, false);
  });

  // 三档画质按钮切换（左栏卡片 + 画布顶栏快捷胶囊联动）
  document.querySelectorAll(".tier-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.activeQuality = card.dataset.quality;
      state.spotlightColorIdx = null;
      refreshAllUI(true, true);
    });
  });
  document.querySelectorAll(".quick-tier-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeQuality = btn.dataset.qtier;
      state.spotlightColorIdx = null;
      refreshAllUI(true, true);
    });
  });

  // 官方 <hose-slider> 铜管长号尺寸推杆实时联动
  const applyCustomMaxSideChange = (nextSide) => {
    if (state.manualEditsByTier[state.activeQuality]) {
      if (!window.confirm("调整长边颗数将重新采样当前档位并覆盖手工改色，是否继续？")) {
        const pat = currentPattern();
        if (pat) {
          syncSizeSliderWidgets(Math.max(pat.grid_width, pat.grid_height));
        }
        return;
      }
    }
    recomputeAllTiers(nextSide);
  };

  if (els.hoseSizeSlider) {
    els.hoseSizeSlider.addEventListener("input", () => {
      const v = Math.round(Number(els.hoseSizeSlider.value) || 58);
      els.customSizeVal.textContent = v;
      els.customSizeRange.value = v;
    });
    els.hoseSizeSlider.addEventListener("change", () => {
      const v = Math.round(Number(els.hoseSizeSlider.value) || 58);
      applyCustomMaxSideChange(v);
    });
  }
  els.customSizeRange.addEventListener("input", () => {
    syncSizeSliderWidgets(els.customSizeRange.value);
  });
  els.customSizeRange.addEventListener("change", () => {
    applyCustomMaxSideChange(parseInt(els.customSizeRange.value, 10));
  });
  els.btnResetSize.addEventListener("click", () => {
    const defDim = state.defaultMaxSides[state.activeQuality] || 58;
    recomputeAllTiers(defDim);
  });

  els.paletteSelect.addEventListener("change", () => {
    if (!confirmDiscardManualEdits("更换拼豆色卡")) {
      els.paletteSelect.value = state.paletteId;
      return;
    }
    state.paletteId = els.paletteSelect.value;
    recomputeAllTiers(null);
  });

  // 官方 <hose-toggle> 灯泡人抠除背景开关
  const handleRemoveBgFlip = (nextChecked) => {
    if (!confirmDiscardManualEdits("切换背景抠除")) {
      syncRemoveBgWidgets(state.removeBg);
      return;
    }
    state.removeBg = Boolean(nextChecked);
    syncRemoveBgWidgets(state.removeBg);
    els.bgTolWrap.classList.toggle("hidden", !state.removeBg);
    recomputeAllTiers(null);
  };
  if (els.hoseRemoveBg) {
    els.hoseRemoveBg.addEventListener("change", () => {
      handleRemoveBgFlip(els.hoseRemoveBg.checked);
    });
  }
  els.chkRemoveBg.addEventListener("change", () => {
    handleRemoveBgFlip(els.chkRemoveBg.checked);
  });

  els.bgTolRange.addEventListener("input", () => {
    els.bgTolVal.textContent = els.bgTolRange.value;
  });
  els.bgTolRange.addEventListener("change", () => {
    state.bgTolerance = parseInt(els.bgTolRange.value, 10);
    recomputeAllTiers(null);
  });

  els.btnBoard29Toggle.addEventListener("click", () => {
    state.showBoard29 = !state.showBoard29;
    els.btnBoard29Toggle.classList.toggle("active", state.showBoard29);
    els.btnBoard29Toggle.setAttribute("aria-pressed", String(state.showBoard29));
    requestRender();
  });
  els.btnRulerToggle.addEventListener("click", () => {
    state.showRuler = !state.showRuler;
    els.btnRulerToggle.classList.toggle("active", state.showRuler);
    els.btnRulerToggle.setAttribute("aria-pressed", String(state.showRuler));
    requestRender();
  });
  els.btnPegboardMat.addEventListener("click", () => {
    state.daylightMat = !state.daylightMat;
    els.btnPegboardMat.classList.toggle("active", state.daylightMat);
    els.btnPegboardMat.setAttribute("aria-pressed", String(state.daylightMat));
    els.canvasViewport.classList.toggle("daylight-mat", state.daylightMat);
    els.matModeLabel.textContent = state.daylightMat ? "深墨衬板" : "羊皮纸板";
    requestRender();
  });

  document.querySelectorAll(".spec-mini-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.beadSpec = btn.dataset.spec;
      document.querySelectorAll(".spec-mini-btn").forEach((b) => b.classList.toggle("active", b === btn));
      if (currentPattern()) updateRightDashboard(currentPattern());
    });
  });

  document.querySelectorAll(".view-switcher .seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prevMode = state.viewMode;
      state.viewMode = btn.dataset.view;
      document.querySelectorAll(".view-switcher .seg-btn").forEach((b) => {
        const isAct = b === btn;
        b.classList.toggle("active", isAct);
        b.setAttribute("aria-selected", String(isAct));
      });
      if (prevMode === "compare" || state.viewMode === "compare") {
        fitPatternToViewport();
      } else {
        requestRender();
      }
    });
  });

  document.querySelectorAll(".skill-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.skillLevel = tab.dataset.skill;
      document.querySelectorAll(".skill-tab").forEach((t) => {
        const isAct = t === tab;
        t.classList.toggle("active", isAct);
        t.setAttribute("aria-selected", String(isAct));
      });
      updateQualityCards();
      if (currentPattern()) updateRightDashboard(currentPattern());
    });
  });

  document.querySelectorAll(".tool-btn").forEach((btn) => {
    btn.addEventListener("click", () => setTool(btn.dataset.tool));
  });

  els.btnBrushColor.addEventListener("click", (e) => {
    e.stopPropagation();
    const isHidden = els.palettePopover.classList.toggle("hidden");
    els.btnBrushColor.setAttribute("aria-expanded", String(!isHidden));
    if (!isHidden) els.paletteSearchInput.focus();
  });
  els.paletteSearchInput.addEventListener("input", () => {
    state.paletteSearch = els.paletteSearchInput.value;
    if (currentPattern()) renderFullPaletteGrid(currentPattern());
  });
  els.fullPaletteGrid.addEventListener("click", (e) => {
    const cellBtn = e.target.closest(".pal-cell-btn");
    if (!cellBtn) return;
    state.selectedColorIdx = parseInt(cellBtn.dataset.palidx, 10);
    setTool("brush");
    els.palettePopover.classList.add("hidden");
    els.btnBrushColor.setAttribute("aria-expanded", "false");
    const pat = currentPattern();
    if (pat) {
      updateBrushColorChip(pat, true);
      renderBomList(pat);
      renderFullPaletteGrid(pat);
    }
  });
  document.addEventListener("click", (e) => {
    if (!els.palettePopover.classList.contains("hidden") && !e.target.closest(".brush-chip-wrap")) {
      els.palettePopover.classList.add("hidden");
      els.btnBrushColor.setAttribute("aria-expanded", "false");
    }
  });

  els.btnUndo.addEventListener("click", undoEdit);
  els.btnRedo.addEventListener("click", redoEdit);

  document.getElementById("btnZoomIn").addEventListener("click", () => zoomBy(1.25));
  document.getElementById("btnZoomOut").addEventListener("click", () => zoomBy(0.8));
  document.getElementById("btnFitView").addEventListener("click", fitPatternToViewport);

  els.canvasViewport.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const rect = els.canvasViewport.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.14 : 0.88;
      const nextZoom = Math.max(0.18, Math.min(7.5, state.zoom * factor));
      const scaleChange = nextZoom / state.zoom;
      state.panX = mx - (mx - state.panX) * scaleChange;
      state.panY = my - (my - state.panY) * scaleChange;
      state.zoom = nextZoom;
      els.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
      requestRender();
    },
    { passive: false }
  );

  els.canvasViewport.addEventListener("mousedown", (e) => {
    if (e.button === 1 || state.activeTool === "pan" || state.spacePressed) {
      state.isDragging = true;
      state.dragStartX = e.clientX - state.panX;
      state.dragStartY = e.clientY - state.panY;
      els.canvasViewport.classList.add("dragging");
      updateViewportCursor();
    } else if (e.button === 0) {
      state.isPainting = true;
      const cellPos = screenToGrid(e.clientX, e.clientY);
      if (cellPos) applyToolAtCell(cellPos.row, cellPos.col);
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (state.isDragging) {
      state.panX = e.clientX - state.dragStartX;
      state.panY = e.clientY - state.dragStartY;
      requestRender();
      return;
    }
    if (state.isPainting) {
      const cellPos = screenToGrid(e.clientX, e.clientY);
      if (cellPos) applyToolAtCell(cellPos.row, cellPos.col);
    }
    const cellPos = screenToGrid(e.clientX, e.clientY);
    const pat = currentPattern();
    if (cellPos && pat) {
      const val = pat.grid[cellPos.row][cellPos.col];
      const bRow = String.fromCharCode(65 + Math.floor(cellPos.row / 29));
      const bCol = Math.floor(cellPos.col / 29) + 1;
      if (val >= 0) {
        const cinfo = pat.palette_lookup[String(val)];
        els.hoverInfo.textContent = `第 ${cellPos.row + 1} 行, 第 ${cellPos.col + 1} 列  ·  ${cinfo.code} ${cinfo.name} (${cinfo.hex})  ·  拼板 ${bRow}${bCol}`;
      } else {
        els.hoverInfo.textContent = `第 ${cellPos.row + 1} 行, 第 ${cellPos.col + 1} 列  ·  [空白针位]  ·  拼板 ${bRow}${bCol}`;
      }
    }
  });

  window.addEventListener("mouseup", () => {
    if (state.isDragging) {
      state.isDragging = false;
      els.canvasViewport.classList.remove("dragging");
      updateViewportCursor();
    }
    if (state.isPainting) {
      state.isPainting = false;
      commitStrokeAndReestimate();
    }
  });

  els.bomSearchInput.addEventListener("input", () => {
    state.bomFilter = els.bomSearchInput.value;
    if (currentPattern()) renderBomList(currentPattern());
  });
  els.btnBomSort.addEventListener("click", () => {
    state.bomSort = state.bomSort === "count" ? "code" : "count";
    els.btnBomSort.textContent = state.bomSort === "count" ? "按数量" : "按色号";
    els.btnBomSort.classList.toggle("active", state.bomSort === "code");
    if (currentPattern()) renderBomList(currentPattern());
  });

  els.bomList.addEventListener("click", (e) => {
    const pat = currentPattern();
    if (!pat) return;

    const chk = e.target.closest(".bom-check");
    if (chk) {
      const pidx = parseInt(chk.dataset.check, 10);
      const doneSet = activeCompletedSet();
      if (chk.checked) doneSet.add(pidx);
      else doneSet.delete(pidx);
      saveCompletedProgress();
      renderBomList(pat);
      updateRightDashboard(pat);
      return;
    }

    const spotBtn = e.target.closest(".bom-spot-btn");
    if (spotBtn) {
      const pidx = parseInt(spotBtn.dataset.spot, 10);
      state.spotlightColorIdx = state.spotlightColorIdx === pidx ? null : pidx;
      renderBomList(pat);
      updateSpotlightBanner(pat);
      requestRender();
      return;
    }

    const selectBtn = e.target.closest(".bom-main-btn");
    if (selectBtn) {
      const pidx = parseInt(selectBtn.dataset.select, 10);
      state.selectedColorIdx = pidx;
      updateBrushColorChip(pat, true);
      renderBomList(pat);
      renderFullPaletteGrid(pat);
      if (state.activeTool === "pan") {
        const cinfo = pat.palette_lookup[String(pidx)];
        showToast(`已选中画笔色号 ${cinfo.code} ${cinfo.name}（按 B 键即可点涂改色）`);
      }
    }
  });

  els.btnClearSpotlight.addEventListener("click", () => {
    state.spotlightColorIdx = null;
    const pat = currentPattern();
    if (pat) {
      renderBomList(pat);
      updateSpotlightBanner(pat);
    }
    requestRender();
  });

  window.addEventListener("keydown", (e) => {
    if (els.agentConfigDialog.open || els.wechatClawDialog.open) return;
    const tag = e.target?.tagName || "";
    const inInput =
      tag === "INPUT" ||
      tag === "SELECT" ||
      tag === "TEXTAREA" ||
      tag.startsWith("HOSE-");
    if (inInput) {
      if (e.key === "Escape") e.target.blur();
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) redoEdit();
      else undoEdit();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
      e.preventDefault();
      redoEdit();
      return;
    }

    if (e.code === "Space" && !state.spacePressed) {
      e.preventDefault();
      state.spacePressed = true;
      updateViewportCursor();
      return;
    }

    const k = e.key.toLowerCase();
    if (k === "h") setTool("pan");
    else if (k === "b") setTool("brush");
    else if (k === "e") setTool("eraser");
    else if (k === "i") setTool("picker");
    else if (k === "=" || k === "+") zoomBy(1.2);
    else if (k === "-") zoomBy(0.84);
    else if (k === "0") fitPatternToViewport();
    else if (e.key === "Escape") {
      if (!els.palettePopover.classList.contains("hidden")) {
        els.palettePopover.classList.add("hidden");
        els.btnBrushColor.setAttribute("aria-expanded", "false");
      } else if (state.spotlightColorIdx !== null) {
        els.btnClearSpotlight.click();
      }
    }
  });

  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") {
      state.spacePressed = false;
      updateViewportCursor();
    }
  });

  els.btnExportPng.addEventListener("click", () => exportFile("png"));
  els.btnExportXlsx.addEventListener("click", () => exportFile("xlsx"));
}

function zoomBy(factor) {
  const rect = els.canvasViewport.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const nextZoom = Math.max(0.18, Math.min(7.5, state.zoom * factor));
  const ratio = nextZoom / state.zoom;
  state.panX = cx - (cx - state.panX) * ratio;
  state.panY = cy - (cy - state.panY) * ratio;
  state.zoom = nextZoom;
  els.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  requestRender();
}

async function exportFile(kind) {
  const pat = currentPattern();
  if (!pat) return;
  showToast(kind === "png" ? "正在生成高清施工图纸..." : "正在生成 Excel 采购清单...");
  try {
    const endpoint = kind === "png" ? "/api/export/png" : "/api/export/xlsx";
    let exportStyle = "code_block";
    if (state.viewMode === "ring") exportStyle = "bead_ring";
    else if (state.viewMode === "flat") exportStyle = "flat_pixel";

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pattern: pat,
        skill_level: state.skillLevel,
        bead_style: exportStyle,
      }),
    });
    if (!res.ok) throw new Error("导出服务响应异常");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const ext = kind === "png" ? "png" : "xlsx";
    a.href = url;
    a.download = `拼豆图纸_${pat.quality_name}_${pat.grid_width}x${pat.grid_height}_${pat.total_beads}颗.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast(kind === "png" ? "高清施工图纸已保存至下载目录" : "Excel 配豆采购表已保存至下载目录");
  } catch (err) {
    showToast("导出失败：" + err.message, true);
  }
}

function startDesktopHeartbeat() {
  let sseConnected = false;
  try {
    const es = new EventSource("/api/session_stream");
    es.onopen = () => {
      sseConnected = true;
    };
    es.onerror = () => {
      sseConnected = false;
    };
    es.addEventListener("wechat_status", (ev) => {
      try {
        applyWechatStatus(JSON.parse(ev.data));
      } catch (_) {}
    });
    es.addEventListener("wechat_sync", (ev) => {
      try {
        handleInboundWechatSync(JSON.parse(ev.data));
      } catch (_) {}
    });
    window._beadSessionStream = es;
  } catch (_) {}

  setInterval(() => {
    if (!sseConnected) {
      fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
    }
  }, 5000);

  window.addEventListener("pagehide", () => {
    if (window._beadSessionStream) {
      window._beadSessionStream.close();
    }
    navigator.sendBeacon("/api/window_closed", "{}");
  });
}

initApp();
