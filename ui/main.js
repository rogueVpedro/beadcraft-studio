/**
 * 拼豆工坊 (BeadCraft Studio) 桌面交互式画布与工时联动前端核心 (Impeccable Polished Edition)
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
  activeTool: "pan",        // pan | brush | eraser | picker
  selectedColorIdx: 0,      // 改色笔当前激活的色号索引
  spotlightColorIdx: null,  // 单色聚光灯跟拼目标色号索引（与改色笔解耦）
  bomFilter: "",
  bomSort: "count",         // count | code
  completedByTier: { simple: new Set(), hd: new Set(), faithful: new Set() },
  undoStacks: { simple: [], hd: [], faithful: [] },
  redoStacks: { simple: [], hd: [], faithful: [] },
  manualEditsByTier: { simple: false, hd: false, faithful: false },

  showBoard29: true,
  showRuler: true,
  daylightMat: false,       // false: 深色高对比底板 | true: 透白实景拼板底色
  craftFocus: false,        // 专注跟拼模式（折叠左侧参数栏）

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
  btnCraftFocus: document.getElementById("btnCraftFocus"),
  craftFocusLabel: document.getElementById("craftFocusLabel"),
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

function showToast(msg, isError = false) {
  els.toast.textContent = msg;
  els.toast.classList.toggle("error", Boolean(isError));
  els.toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => els.toast.classList.add("hidden"), isError ? 4200 : 2600);
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

// ---------------------------------------------------------------------------
// 初始化与后端通信
// ---------------------------------------------------------------------------
async function initApp() {
  startDesktopHeartbeat();
  bindEvents();
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

    if (meta.samples.length > 0) {
      await loadSample(meta.samples[0].id);
    }
  } catch (err) {
    showToast("初始化连接失败，请刷新窗口重试：" + err.message, true);
  }
}

async function loadSample(sampleId) {
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
    applyLoadedImageResult(data, true);
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
    applyLoadedImageResult(data, true);
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
    refreshAllUI(customMaxSide === null);
  } catch (err) {
    showToast("重新生成失败：" + err.message, true);
  } finally {
    setLoading(false);
  }
}

function applyLoadedImageResult(data, fitView = true) {
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

  refreshAllUI(fitView);
}

// ---------------------------------------------------------------------------
// UI 状态同步更新
// ---------------------------------------------------------------------------
function refreshAllUI(fitAfter = false) {
  updateQualityCards();
  const pat = currentPattern();
  if (!pat) return;

  const maxDim = Math.max(pat.grid_width, pat.grid_height);
  els.customSizeRange.value = maxDim;
  els.customSizeVal.textContent = maxDim;

  const defDim = state.defaultMaxSides[state.activeQuality] || 58;
  els.customModifiedTag.classList.toggle("hidden", maxDim === defDim);

  document.querySelectorAll(".tier-card").forEach((card) => {
    const isAct = card.dataset.quality === state.activeQuality;
    card.classList.toggle("active", isAct);
    card.setAttribute("aria-checked", isAct ? "true" : "false");
  });

  updateBrushColorChip(pat);
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

function updateBrushColorChip(pat) {
  const cinfo = pat.palette_lookup[String(state.selectedColorIdx)] || Object.values(pat.palette_lookup)[0];
  if (!cinfo) return;
  els.brushSwatchDot.style.background = cinfo.hex;
  els.brushColorCode.textContent = `${cinfo.code} ${cinfo.name}`;
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
  els.remainingTimeText.textContent = doneBeads >= pat.total_beads ? "全部色号摆豆已完成" : `剩余约 ${remTxt}`;
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
    if (aDone !== bDone) return aDone - bDone; // 已完成的色号自动沉底，方便专注剩余色号
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
// Canvas 拼豆渲染引擎（支持透白实景拼板 & 深色高对比双底板）
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
  const boardBg = isDaylight ? "#f5f7fa" : "#1b2230";
  const pegHoleFill = isDaylight ? "#dfe5ee" : "#141923";
  const emptyPinFill = isDaylight ? "rgba(100, 116, 139, 0.28)" : "rgba(148, 163, 184, 0.18)";

  let ox = state.panX;
  const oy = state.panY;

  if (state.viewMode === "compare" && state.sourceImgObj) {
    ctx.save();
    ctx.fillStyle = boardBg;
    ctx.fillRect(ox - 2, oy - 2, boardW + 4, boardH + 4);
    ctx.drawImage(state.sourceImgObj, ox, oy, boardW, boardH);
    ctx.fillStyle = "rgba(17, 21, 28, 0.84)";
    ctx.fillRect(ox + 8, oy + 8, 76, 24);
    ctx.fillStyle = "#f3f6fb";
    ctx.font = "600 12px 'Microsoft YaHei UI', sans-serif";
    ctx.fillText("原始图片", ox + 18, oy + 24);
    ctx.restore();
    ox = state.panX + boardW + cell * 3;
  }

  ctx.save();
  ctx.shadowColor = isDaylight ? "rgba(15, 23, 42, 0.18)" : "rgba(0, 0, 0, 0.48)";
  ctx.shadowBlur = 20;
  ctx.shadowOffsetY = 6;
  ctx.fillStyle = boardBg;
  ctx.fillRect(ox, oy, boardW, boardH);
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
    ctx.font = `700 ${Math.max(8, Math.floor(cell * 0.39))}px "Microsoft YaHei UI", sans-serif`;
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
      ctx.globalAlpha = dimmed ? 0.13 : 1.0;

      if (state.viewMode === "ring") {
        const cx = x0 + cell * 0.5;
        const cy = y0 + cell * 0.5;
        const outerR = cell * 0.465;
        const innerR = cell * 0.185;

        ctx.fillStyle = cinfo.hex;
        ctx.beginPath();
        ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
        ctx.fill();

        if (isDaylight && cell >= 8) {
          ctx.strokeStyle = "rgba(15, 23, 42, 0.14)";
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }

        if (cell >= 8) {
          ctx.strokeStyle = "rgba(255,255,255,0.28)";
          ctx.lineWidth = Math.max(1, cell * 0.06);
          ctx.beginPath();
          ctx.arc(cx, cy, outerR * 0.76, Math.PI * 1.1, Math.PI * 1.75);
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
        const pad = state.viewMode === "flat" ? 0 : 0.4;
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

  // 5 格辅助线与单格细网格线
  if (cell >= 10 || state.viewMode === "code") {
    ctx.lineWidth = 1;
    const majorGrid = isDaylight ? "rgba(71, 85, 105, 0.34)" : "rgba(148, 163, 184, 0.34)";
    const minorGrid = isDaylight ? "rgba(100, 116, 139, 0.16)" : "rgba(148, 163, 184, 0.14)";

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

  // 29×29 标准大模板分界线
  if (state.showBoard29) {
    ctx.strokeStyle = isDaylight ? "rgba(220, 38, 38, 0.85)" : "rgba(248, 113, 113, 0.88)";
    ctx.lineWidth = 2;
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

  // 行列数字坐标尺
  if (state.showRuler && cell >= 9) {
    const rulerNormal = isDaylight ? "#334155" : "#95a4be";
    const ruler29 = isDaylight ? "#dc2626" : "#f87171";
    ctx.font = `600 ${Math.min(12, Math.max(10, Math.floor(cell * 0.48)))}px "Segoe UI", sans-serif`;
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
// 坐标转换、手工改色与完整撤销/重做栈 (Ctrl+Z / Ctrl+Y)
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
      updateBrushColorChip(pat);
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
    refreshAllUI(false);
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
// 事件绑定
// ---------------------------------------------------------------------------
function bindEvents() {
  window.addEventListener("resize", resizeCanvasToContainer);

  // 专注跟拼模式（折叠左侧参数栏，最大化拼板画布）
  els.btnCraftFocus.addEventListener("click", () => {
    state.craftFocus = !state.craftFocus;
    els.workspaceGrid.classList.toggle("craft-focus", state.craftFocus);
    els.btnCraftFocus.setAttribute("aria-pressed", String(state.craftFocus));
    els.craftFocusLabel.textContent = state.craftFocus ? "展开设置" : "专注跟拼";
    resizeCanvasToContainer();
    fitPatternToViewport();
  });

  // 上传与键盘无障碍支持 (防止冒泡导致重复上传)
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
    const items = e.clipboardData?.items || [];
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        uploadImageFile(item.getAsFile());
        break;
      }
    }
  });

  // 示例切换
  els.sampleButtons.addEventListener("click", (e) => {
    const btn = e.target.closest(".sample-pill");
    if (!btn) return;
    if (!confirmDiscardManualEdits("切换示例图案")) return;
    document.querySelectorAll(".sample-pill").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadSample(btn.dataset.sample);
  });

  // 三档画质按钮切换（各自保留跟拼勾选进度与撤销历史，绝不误清空！）
  document.querySelectorAll(".tier-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.activeQuality = card.dataset.quality;
      state.spotlightColorIdx = null;
      refreshAllUI(true);
    });
  });

  // 尺寸微调与单档重置
  els.customSizeRange.addEventListener("input", () => {
    els.customSizeVal.textContent = els.customSizeRange.value;
  });
  els.customSizeRange.addEventListener("change", () => {
    if (state.manualEditsByTier[state.activeQuality]) {
      if (!window.confirm("调整长边颗数将重新采样当前档位并覆盖手工改色，是否继续？")) {
        const pat = currentPattern();
        if (pat) {
          const curMax = Math.max(pat.grid_width, pat.grid_height);
          els.customSizeRange.value = curMax;
          els.customSizeVal.textContent = curMax;
        }
        return;
      }
    }
    recomputeAllTiers(parseInt(els.customSizeRange.value, 10));
  });
  els.btnResetSize.addEventListener("click", () => {
    const defDim = state.defaultMaxSides[state.activeQuality] || 58;
    recomputeAllTiers(defDim);
  });

  // 色卡与去背景设置
  els.paletteSelect.addEventListener("change", () => {
    if (!confirmDiscardManualEdits("更换拼豆色卡")) {
      els.paletteSelect.value = state.paletteId;
      return;
    }
    state.paletteId = els.paletteSelect.value;
    recomputeAllTiers(null);
  });
  els.chkRemoveBg.addEventListener("change", () => {
    if (!confirmDiscardManualEdits("切换背景抠除")) {
      els.chkRemoveBg.checked = state.removeBg;
      return;
    }
    state.removeBg = els.chkRemoveBg.checked;
    els.bgTolWrap.classList.toggle("hidden", !state.removeBg);
    recomputeAllTiers(null);
  });
  els.bgTolRange.addEventListener("input", () => {
    els.bgTolVal.textContent = els.bgTolRange.value;
  });
  els.bgTolRange.addEventListener("change", () => {
    state.bgTolerance = parseInt(els.bgTolRange.value, 10);
    recomputeAllTiers(null);
  });

  // 画布辅助线与透白实景底板切换
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
    els.matModeLabel.textContent = state.daylightMat ? "深色底板" : "实景白板";
    requestRender();
  });

  // 成品尺寸豆子规格切换
  document.querySelectorAll(".spec-mini-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.beadSpec = btn.dataset.spec;
      document.querySelectorAll(".spec-mini-btn").forEach((b) => b.classList.toggle("active", b === btn));
      if (currentPattern()) updateRightDashboard(currentPattern());
    });
  });

  // 顶部四视图切换 (同步 aria-selected)
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

  // 熟练度三档切换 (同步 aria-selected)
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

  // 工具条、全色卡选择器、撤销重做与缩放
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
      updateBrushColorChip(pat);
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

  // 画布鼠标按下（支持按住空格键在画笔模式下临时抓手平移！）
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

  // BOM 筛选、排序及三大独立操作（勾选完成 / 选作画笔颜色 / 单色聚光灯高亮）
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
      updateBrushColorChip(pat);
      renderBomList(pat);
      renderFullPaletteGrid(pat);
      if (state.activeTool === "pan") {
        const cinfo = pat.palette_lookup[String(pidx)];
        showToast(`已选中画笔色号 ${cinfo.code} ${cinfo.name}（按 B 键即可点涂改色，点击右侧靶心图标可单色高亮）`);
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

  // 全键盘快捷键支持 (Ctrl+Z / Ctrl+Y / 空格抓手 / H B E I / + - 0 / Esc)
  window.addEventListener("keydown", (e) => {
    const inInput = e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA";
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

  // 导出 PNG 图纸（忠实对应当前所选视图：立体圆环 / 熨烫成品 / 施工色号）与 Excel 清单
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
    window._beadSessionStream = es;
  } catch (_) {}

  // 仅当 SSE 未建立连接时才使用 HTTP 轮询兜底，避免冗余请求
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
