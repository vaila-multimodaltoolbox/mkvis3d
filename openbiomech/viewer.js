"use strict";
const $ = id => document.getElementById(id);
const boot = JSON.parse($("trial-data").textContent);
let embeddedTemplates = {};
try {
  const tEl = $("skeleton-templates-data");
  if (tEl && tEl.textContent.trim()) {
    embeddedTemplates = JSON.parse(tEl.textContent);
  }
} catch (e) {
  console.warn("Could not parse embedded skeleton templates:", e);
}

const token = location.hash.slice(1);

let trial = null, frame = 0, playing = false, lastTick = 0, elapsed = 0;
let yaw = -0.45, pitch = 0.22, zoom = 1, pan = [0, 0], center = [0, 0, 0], span = 1;
let distances = [], activeMarkerIndex = 0, showDistance = true;
let skeletonPairs = [];
let activeSkeletonTemplate = "none";
let loadedCustomTemplate = null;
let popoutWindows = {};

// Visual3D LCS and Signal Conditioning State
let rawLoadedXYZ = null;
let currentLCS = { ap: "+Y", axial: "+Z" };
let activeFilterConfig = null;
let filterPreviewActive = false;
let filterPreviewSeries = null;

// Force Platforms & Kinetics (Visual3D & Mokka Parity)
let showForcePlates = true;
let showForceVectors = true;
let forceVectorScale = 0.001; // 1.0 mm per N (0.001 m/N)
let forceThreshold = 15.0; // 15 N
let rawForcePlates = null;

// Marker Appearance Palette (matching /home/preto/data/vaila/vaila/viewc3d.py)
const MARKER_PALETTE = [
  { name: "Orange", hex: "#f97316" }, // [1.0, 0.65, 0.0] - Default in viewc3d.py
  { name: "Blue", hex: "#3b82f6" },   // [0.0, 0.5, 1.0]
  { name: "Green", hex: "#22c55e" },  // [0.0, 1.0, 0.0]
  { name: "Red", hex: "#ef4444" },    // [1.0, 0.0, 0.0]
  { name: "White", hex: "#ffffff" },  // [1.0, 1.0, 1.0]
  { name: "Yellow", hex: "#eab308" }, // [1.0, 1.0, 0.0]
  { name: "Purple", hex: "#a855f7" }, // [0.5, 0.0, 1.0]
  { name: "Cyan", hex: "#06b6d4" },   // [0.0, 1.0, 1.0]
  { name: "Pink", hex: "#ec4899" },   // [1.0, 0.0, 1.0]
  { name: "Gray", hex: "#6b7280" },   // [0.5, 0.5, 0.5]
  { name: "Black", hex: "#111827" },  // [0.0, 0.0, 0.0]
];

let markerSize = 3.5;
let markerColor = "auto";
let markerPaletteIndex = -1;

function setMarkerSize(size) {
  markerSize = Math.max(1, Math.min(15, Number(size) || 3.5));
  if ($("marker-size-slider")) $("marker-size-slider").value = String(markerSize);
  if ($("marker-size-val")) $("marker-size-val").textContent = `${markerSize.toFixed(1)} px`;
  draw();
  saveSessionState();
}

function setMarkerColor(colorHex, colorName) {
  markerColor = colorHex;
  if (!colorName) {
    if (colorHex === "auto") {
      colorName = "Default";
    } else {
      const match = MARKER_PALETTE.find(p => p.hex.toLowerCase() === colorHex.toLowerCase());
      colorName = match ? match.name : colorHex;
    }
  }
  if ($("marker-color-name-badge")) $("marker-color-name-badge").textContent = colorName;
  if ($("marker-color-custom") && colorHex !== "auto") $("marker-color-custom").value = colorHex;
  document.querySelectorAll(".color-swatch-btn").forEach(btn => {
    btn.classList.toggle("selected", btn.dataset.color === colorHex);
  });
  status(`Marker color: ${colorName}`);
  draw();
  saveSessionState();
}

function cycleMarkerColor() {
  markerPaletteIndex = (markerPaletteIndex + 1) % (MARKER_PALETTE.length + 1);
  if (markerPaletteIndex === MARKER_PALETTE.length) {
    setMarkerColor("auto", "Default (Theme)");
  } else {
    const item = MARKER_PALETTE[markerPaletteIndex];
    setMarkerColor(item.hex, item.name);
  }
}

function resetMarkerStyle() {
  markerPaletteIndex = -1;
  setMarkerSize(3.5);
  setMarkerColor("auto", "Default");
}

let currentTheme = "dark";
try {
  const saved = localStorage.getItem("mkvis3d_theme") || sessionStorage.getItem("mkvis3d_theme");
  if (saved === "light" || saved === "dark") {
    currentTheme = saved;
  }
} catch (e) {}

function setTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", currentTheme);
  try {
    localStorage.setItem("mkvis3d_theme", currentTheme);
    sessionStorage.setItem("mkvis3d_theme", currentTheme);
  } catch (e) {}

  const themeIcon = $("theme-icon");
  const themeLabel = $("theme-label");
  const btnToggle = $("btn-toggle-theme");
  if (themeIcon) themeIcon.textContent = currentTheme === "light" ? "☀️" : "🌙";
  if (themeLabel) themeLabel.textContent = currentTheme === "light" ? "Light" : "Dark";
  if (btnToggle) {
    btnToggle.title = currentTheme === "light"
      ? "Light Mode Active (Click or Alt+T for Dark Mode)"
      : "Dark Mode Active (Click or Alt+T for Light Mode)";
  }

  // Update View menu items
  if ($("action-theme-dark")) {
    $("action-theme-dark").textContent = (currentTheme === "dark" ? "✓ " : "  ") + "Dark Mode (Escuro)";
  }
  if ($("action-theme-light")) {
    $("action-theme-light").textContent = (currentTheme === "light" ? "✓ " : "  ") + "Light Mode (Claro)";
  }

  // Update Options menu items
  if ($("action-opt-theme-dark")) {
    $("action-opt-theme-dark").textContent = (currentTheme === "dark" ? "✓ " : "  ") + "Dark Mode (Escuro)";
  }
  if ($("action-opt-theme-light")) {
    $("action-opt-theme-light").textContent = (currentTheme === "light" ? "✓ " : "  ") + "Light Mode (Claro)";
  }

  const autoSwatch = document.querySelector('.color-swatch-btn[data-color="auto"]');
  if (autoSwatch) {
    autoSwatch.style.background = currentTheme === "light" ? "#475569" : "#9bbed7";
  }

  // Synchronize detached/popout windows
  for (const paneId in popoutWindows) {
    const popWin = popoutWindows[paneId];
    if (popWin && !popWin.closed && popWin.document && popWin.document.documentElement) {
      popWin.document.documentElement.setAttribute("data-theme", currentTheme);
      syncPopoutContent(paneId);
    }
  }

  // Redraw canvases with new theme palette
  draw();
  saveSessionState();
}

function toggleTheme() {
  setTheme(currentTheme === "dark" ? "light" : "dark");
}

const canvas = $("scene"), ctx = canvas.getContext("2d");
const graph1 = $("graph"), gx1 = graph1.getContext("2d");
const graph2 = $("graph2") ? $("graph2").getContext("2d") : null;

const valid = p => Array.isArray(p) && p.length === 3 && p.every(Number.isFinite);

function status(message, error = false) {
  if (!$("status")) return;
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}

function orient(p) {
  const up = $("up") ? $("up").value : "z";
  return up === "y" ? [p[0], -p[2], p[1]] : up === "x" ? [p[1], p[2], p[0]] : p;
}

function projectOriented(p, w = canvas.clientWidth, h = canvas.clientHeight) {
  const diff = [p[0] - center[0], p[1] - center[1], p[2] - center[2]];
  const x = Math.cos(yaw) * diff[0] - Math.sin(yaw) * diff[1];
  const depth = Math.sin(yaw) * diff[0] + Math.cos(yaw) * diff[1];
  const z = Math.cos(pitch) * diff[2] - Math.sin(pitch) * depth;
  const s = Math.min(w, h) * 0.75 / span * zoom;
  return [w / 2 + x * s + pan[0], h / 2 - z * s + pan[1], depth];
}

function project(raw, w = canvas.clientWidth, h = canvas.clientHeight) {
  return projectOriented(orient(raw), w, h);
}

function line(a, b, color, width = 1, targetCtx = ctx, w = canvas.clientWidth, h = canvas.clientHeight) {
  const p = project(a, w, h), q = project(b, w, h);
  targetCtx.strokeStyle = color;
  targetCtx.lineWidth = width;
  targetCtx.beginPath();
  targetCtx.moveTo(p[0], p[1]);
  targetCtx.lineTo(q[0], q[1]);
  targetCtx.stroke();
}

function fit() {
  if (!trial) return;
  let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  const stride = Math.max(1, Math.floor(trial.xyz.length / 50));
  for (let f = 0; f < trial.xyz.length; f += stride) {
    for (const raw of trial.xyz[f]) {
      if (!valid(raw)) continue;
      const p = orient(raw);
      for (let j = 0; j < 3; j++) {
        lo[j] = Math.min(lo[j], p[j]);
        hi[j] = Math.max(hi[j], p[j]);
      }
    }
  }
  // Include force plate corners in scene bounds
  if (trial.force_plates && trial.force_plates.length && showForcePlates) {
    for (const fp of trial.force_plates) {
      if (!fp.corners) continue;
      for (const corner of fp.corners) {
        const p = orient(corner);
        for (let j = 0; j < 3; j++) {
          lo[j] = Math.min(lo[j], p[j]);
          hi[j] = Math.max(hi[j], p[j]);
        }
      }
    }
  }
  center = lo.map((v, j) => (v + hi[j]) / 2);
  span = Math.max(...hi.map((v, j) => v - lo[j]), 0.01);
  zoom = 1;
  pan = [0, 0];
  draw();
}

// Compute floor height for ground grid
function getFloorHeight() {
  if (!trial) return 0;
  const option = document.querySelector("[data-floor].active");
  const mode = option ? option.dataset.floor : "auto";
  if (mode === "origin") return 0;

  // If force plates are present, ground surface is at plate level
  if (trial.force_plates && trial.force_plates.length && showForcePlates) {
    let minFpZ = Infinity;
    for (const fp of trial.force_plates) {
      if (fp.corners) {
        for (const corner of fp.corners) {
          const p = orient(corner);
          minFpZ = Math.min(minFpZ, p[2]);
        }
      }
    }
    if (Number.isFinite(minFpZ)) return minFpZ;
  }

  let minH = Infinity;
  for (const raw of trial.xyz[frame] || []) {
    if (valid(raw)) {
      const p = orient(raw);
      minH = Math.min(minH, p[2]);
    }
  }
  return Number.isFinite(minH) ? minH : 0;
}

// 3D Ground Plane Grid
function drawGroundGrid(targetCtx = ctx, w = canvas.clientWidth, h = canvas.clientHeight) {
  if (!$("grid") || !$("grid").checked) return;
  const floorH = getFloorHeight();
  const gridSize = Math.max(span * 1.5, 2.0);
  const step = gridSize > 5 ? 1.0 : gridSize > 2 ? 0.5 : 0.2;
  const count = Math.min(20, Math.ceil(gridSize / step));
  const extent = count * step;
  const isLight = currentTheme === "light";

  targetCtx.lineWidth = 1;
  for (let i = -count; i <= count; i++) {
    const x = i * step;
    const isCenter = i === 0;
    targetCtx.strokeStyle = isCenter
      ? (isLight ? "rgba(220, 38, 38, 0.7)" : "rgba(239, 134, 134, 0.6)")
      : (isLight ? "rgba(100, 116, 139, 0.25)" : "rgba(75, 105, 135, 0.25)");
    targetCtx.lineWidth = isCenter ? 1.5 : 1;
    const p1 = projectOriented([center[0] + x, center[1] - extent, floorH], w, h);
    const p2 = projectOriented([center[0] + x, center[1] + extent, floorH], w, h);
    targetCtx.beginPath();
    targetCtx.moveTo(p1[0], p1[1]);
    targetCtx.lineTo(p2[0], p2[1]);
    targetCtx.stroke();
  }
  for (let i = -count; i <= count; i++) {
    const y = i * step;
    const isCenter = i === 0;
    targetCtx.strokeStyle = isCenter
      ? (isLight ? "rgba(22, 163, 74, 0.7)" : "rgba(130, 217, 157, 0.6)")
      : (isLight ? "rgba(100, 116, 139, 0.25)" : "rgba(75, 105, 135, 0.25)");
    targetCtx.lineWidth = isCenter ? 1.5 : 1;
    const p1 = projectOriented([center[0] - extent, center[1] + y, floorH], w, h);
    const p2 = projectOriented([center[0] + extent, center[1] + y, floorH], w, h);
    targetCtx.beginPath();
    targetCtx.moveTo(p1[0], p1[1]);
    targetCtx.lineTo(p2[0], p2[1]);
    targetCtx.stroke();
  }
}

// Built-in fallback Vicon squat skeleton template
const VICON_SQUAT_TEMPLATE = {
  schema: "vicon_squat",
  connections: [
    ["D_barra2", "D_barra1"], ["D_barra1", "barra_centro"],
    ["barra_centro", "E_barra1"], ["E_barra1", "E_barra2"],
    ["D_trocanter", "D_joelho"], ["D_joelho", "D_tornozelo"],
    ["E_trocanter", "E_joelho"], ["E_joelho", "E_tornozelo"],
    ["D_trocanter", "E_trocanter"],
    ["D_acromio", "E_acromio"],
    ["D_acromio", "D_trocanter"], ["E_acromio", "E_trocanter"],
    ["D_acromio", "D_mao"], ["E_acromio", "E_mao"]
  ]
};

// Skeleton initialization - does NOT auto-load pairs, user loads explicitly
function initSkeleton(labels) {
  skeletonPairs = [];
  activeSkeletonTemplate = "none";
  if ($("skeleton-template-select")) $("skeleton-template-select").value = "none";
  const badge = $("skeleton-status-badge");
  if (badge) {
    badge.textContent = "No skeleton";
    badge.style.color = "var(--text-muted)";
  }
}

// Apply chosen skeleton template to current trial
function applySkeletonTemplate(templateObj) {
  if (!trial) return 0;
  skeletonPairs = [];
  if (!templateObj || !Array.isArray(templateObj.connections)) {
    draw();
    return 0;
  }
  const labelMap = new Map();
  trial.labels.forEach((lbl, idx) => {
    labelMap.set(lbl.toLowerCase().trim(), idx);
    labelMap.set(`p${idx + 1}`, idx);
  });

  const tKeypoints = Array.isArray(templateObj.keypoints) ? templateObj.keypoints : [];
  const tKeypointToIdx = new Map();
  tKeypoints.forEach((kpName, kpIdx) => {
    tKeypointToIdx.set(kpName.toLowerCase().trim(), kpIdx);
  });

  for (const conn of templateObj.connections) {
    if (!Array.isArray(conn) || conn.length < 2) continue;
    const aStr = String(conn[0]).toLowerCase().trim();
    const bStr = String(conn[1]).toLowerCase().trim();
    let idxA = -1, idxB = -1;

    if (labelMap.has(aStr)) idxA = labelMap.get(aStr);
    else if (tKeypointToIdx.has(aStr)) {
      const pIdx = tKeypointToIdx.get(aStr);
      if (pIdx < trial.labels.length) idxA = pIdx;
    }

    if (labelMap.has(bStr)) idxB = labelMap.get(bStr);
    else if (tKeypointToIdx.has(bStr)) {
      const pIdx = tKeypointToIdx.get(bStr);
      if (pIdx < trial.labels.length) idxB = pIdx;
    }

    if (idxA >= 0 && idxB >= 0 && idxA < trial.labels.length && idxB < trial.labels.length && idxA !== idxB) {
      skeletonPairs.push([idxA, idxB]);
    }
  }

  if ($("bones")) $("bones").checked = skeletonPairs.length > 0;
  const badge = $("skeleton-status-badge");
  if (badge) {
    badge.textContent = skeletonPairs.length > 0 ? `${skeletonPairs.length} conexões` : "0 conexões";
    badge.style.color = skeletonPairs.length > 0 ? "var(--accent)" : "var(--text-muted)";
  }
  draw();
  return skeletonPairs.length;
}

function drawSkeleton(pts, targetCtx = ctx, w = canvas.clientWidth, h = canvas.clientHeight) {
  if (!$("bones") || !$("bones").checked || !skeletonPairs.length || !pts) return;
  const boneColor = currentTheme === "light" ? "rgba(30, 80, 140, 0.85)" : "rgba(110, 160, 205, 0.75)";
  for (const [i, j] of skeletonPairs) {
    if (valid(pts[i]) && valid(pts[j])) {
      line(pts[i], pts[j], boneColor, 2, targetCtx, w, h);
    }
  }
}

// Draw 3D Physical Force Platforms on Floor
function drawForcePlates(targetCtx = ctx, w = canvas.clientWidth, h = canvas.clientHeight) {
  if (!trial || !trial.force_plates || !trial.force_plates.length || !showForcePlates) return;
  const isLight = currentTheme === "light";
  const fillColor = isLight ? "rgba(203, 213, 225, 0.45)" : "rgba(30, 41, 59, 0.55)";
  const strokeColor = isLight ? "rgba(100, 116, 139, 0.85)" : "rgba(71, 85, 105, 0.9)";
  const gridColor = isLight ? "rgba(148, 163, 184, 0.35)" : "rgba(51, 65, 85, 0.45)";
  const labelColor = isLight ? "#334155" : "#94a3b8";

  for (const fp of trial.force_plates) {
    if (!fp.corners || fp.corners.length < 4) continue;
    const c = fp.corners;
    const p0 = project(c[0], w, h), p1 = project(c[1], w, h);
    const p2 = project(c[2], w, h), p3 = project(c[3], w, h);

    if (!Number.isFinite(p0[0]) || !Number.isFinite(p1[0]) || !Number.isFinite(p2[0]) || !Number.isFinite(p3[0])) continue;

    // Draw plate surface quad
    targetCtx.beginPath();
    targetCtx.moveTo(p0[0], p0[1]);
    targetCtx.lineTo(p1[0], p1[1]);
    targetCtx.lineTo(p2[0], p2[1]);
    targetCtx.lineTo(p3[0], p3[1]);
    targetCtx.closePath();

    targetCtx.fillStyle = fillColor;
    targetCtx.fill();
    targetCtx.strokeStyle = strokeColor;
    targetCtx.lineWidth = 1.5;
    targetCtx.stroke();

    // Internal cross markings
    const midTop = [(c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2, (c[0][2] + c[1][2]) / 2];
    const midBot = [(c[3][0] + c[2][0]) / 2, (c[3][1] + c[2][1]) / 2, (c[3][2] + c[2][2]) / 2];
    const midLeft = [(c[0][0] + c[3][0]) / 2, (c[0][1] + c[3][1]) / 2, (c[0][2] + c[3][2]) / 2];
    const midRight = [(c[1][0] + c[2][0]) / 2, (c[1][1] + c[2][1]) / 2, (c[1][2] + c[2][2]) / 2];

    const pmTop = project(midTop, w, h), pmBot = project(midBot, w, h);
    const pmLeft = project(midLeft, w, h), pmRight = project(midRight, w, h);

    targetCtx.strokeStyle = gridColor;
    targetCtx.lineWidth = 1;
    targetCtx.beginPath();
    targetCtx.moveTo(pmTop[0], pmTop[1]);
    targetCtx.lineTo(pmBot[0], pmBot[1]);
    targetCtx.moveTo(pmLeft[0], pmLeft[1]);
    targetCtx.lineTo(pmRight[0], pmRight[1]);
    targetCtx.stroke();

    // Plate Label at center
    const center3D = [
      (c[0][0] + c[2][0]) / 2,
      (c[0][1] + c[2][1]) / 2,
      (c[0][2] + c[2][2]) / 2,
    ];
    const pc = project(center3D, w, h);
    targetCtx.fillStyle = labelColor;
    targetCtx.font = "bold 11px system-ui, sans-serif";
    targetCtx.textAlign = "center";
    targetCtx.textBaseline = "middle";
    targetCtx.fillText(fp.name || `FP${fp.id + 1}`, pc[0], pc[1]);
    targetCtx.textAlign = "left";
    targetCtx.textBaseline = "alphabetic";
  }
}

// Draw Dynamic Ground Reaction Force (GRF) Vectors & COP
function drawForceVectors(targetCtx = ctx, w = canvas.clientWidth, h = canvas.clientHeight) {
  if (!trial || !trial.force_plates || !trial.force_plates.length || !showForceVectors) return;
  const isLight = currentTheme === "light";
  const vectorColor = isLight ? "#ea580c" : "#f97316";
  const copColor = isLight ? "#eab308" : "#facc15";

  let totalFz = 0;
  const plateReadouts = [];

  for (const fp of trial.force_plates) {
    if (!fp.cop || !fp.force) continue;
    const cop = fp.cop[frame];
    const force = fp.force[frame];
    const contact = fp.contact ? fp.contact[frame] : true;

    if (!cop || !valid(cop) || !force || !valid(force) || !contact) continue;

    const fz = force[2];
    const fMag = Math.hypot(force[0], force[1], force[2]);
    if (Math.abs(fz) < forceThreshold || fMag < 1.0) continue;

    totalFz += fz;
    plateReadouts.push(`${fp.name}: ${Math.round(fz)} N`);

    // Project Center of Pressure
    const pCop = project(cop, w, h);

    // Tip of vector in 3D (meters)
    const tip3D = [
      cop[0] + force[0] * forceVectorScale,
      cop[1] + force[1] * forceVectorScale,
      cop[2] + force[2] * forceVectorScale,
    ];
    const pTip = project(tip3D, w, h);

    if (!Number.isFinite(pCop[0]) || !Number.isFinite(pTip[0])) continue;

    // Draw COP marker on plate surface
    targetCtx.beginPath();
    targetCtx.arc(pCop[0], pCop[1], 4.5, 0, Math.PI * 2);
    targetCtx.fillStyle = copColor;
    targetCtx.fill();
    targetCtx.strokeStyle = isLight ? "#0f172a" : "#ffffff";
    targetCtx.lineWidth = 1.5;
    targetCtx.stroke();

    // Draw 3D Force Vector Shaft
    targetCtx.beginPath();
    targetCtx.moveTo(pCop[0], pCop[1]);
    targetCtx.lineTo(pTip[0], pTip[1]);
    targetCtx.strokeStyle = vectorColor;
    targetCtx.lineWidth = 3.5;
    targetCtx.stroke();

    // Draw Arrowhead at tip
    const dx = pTip[0] - pCop[0], dy = pTip[1] - pCop[1];
    const len = Math.hypot(dx, dy);
    if (len > 4) {
      const angle = Math.atan2(dy, dx);
      const headLen = Math.min(14, len * 0.4);
      const headAngle = Math.PI / 6;

      targetCtx.beginPath();
      targetCtx.moveTo(pTip[0], pTip[1]);
      targetCtx.lineTo(
        pTip[0] - headLen * Math.cos(angle - headAngle),
        pTip[1] - headLen * Math.sin(angle - headAngle)
      );
      targetCtx.lineTo(
        pTip[0] - headLen * Math.cos(angle + headAngle),
        pTip[1] - headLen * Math.sin(angle + headAngle)
      );
      targetCtx.closePath();
      targetCtx.fillStyle = vectorColor;
      targetCtx.fill();
    }

    // Force magnitude readout next to arrow tip
    targetCtx.font = "bold 11px system-ui, sans-serif";
    targetCtx.fillStyle = isLight ? "#0f172a" : "#f0f6fc";
    targetCtx.fillText(`${Math.round(fMag)} N`, pTip[0] + 8, pTip[1] - 4);
  }

  // Update sidebar readouts
  if ($("total-fz-val")) {
    $("total-fz-val").textContent = `${Math.round(totalFz)} N`;
  }
  if ($("plate-mini-readouts")) {
    $("plate-mini-readouts").textContent = plateReadouts.length > 0 ? plateReadouts.join(" · ") : "No active contact";
  }
}

// Render 3D scene to any canvas context (main scene or detached popout window)
function drawSceneToContext(targetCtx, w, h) {
  targetCtx.clearRect(0, 0, w, h);
  if (!trial) return;

  drawGroundGrid(targetCtx, w, h);

  // Draw Force Platforms on the floor
  drawForcePlates(targetCtx, w, h);

  // Draw Ground Reaction Force Vectors & Center of Pressure
  drawForceVectors(targetCtx, w, h);

  const pts = trial.xyz[frame] || [];
  const activeIdx = activeMarkerIndex;
  const a = Number($("marker-a") ? $("marker-a").value : 0);
  const b = Number($("marker-b") ? $("marker-b").value : 1);
  const isLight = currentTheme === "light";

  // Coordinate axes at origin
  const origin = [0, 0, 0];
  const axesColors = isLight
    ? ["#dc2626", "#16a34a", "#2563eb"]
    : ["#ef8686", "#82d99d", "#7faeeb"];
  const axesLabels = ["X", "Y", "Z"];
  for (let i = 0; i < 3; i++) {
    const end = [0, 0, 0]; end[i] = span * 0.22;
    line(origin, end, axesColors[i], 2, targetCtx, w, h);
    const p = project(end, w, h);
    targetCtx.fillStyle = axesColors[i];
    targetCtx.font = "bold 11px system-ui, sans-serif";
    targetCtx.fillText(axesLabels[i], p[0] + 5, p[1]);
  }

  // Draw Skeleton Bones
  drawSkeleton(pts, targetCtx, w, h);

  // Trajectory Trail of active marker
  if ($("trail") && $("trail").checked && activeIdx >= 0 && activeIdx < trial.labels.length) {
    const trailColor = isLight ? "#0f766e" : "#35827c";
    for (let f = Math.max(1, frame - 120); f <= frame; f++) {
      const p = trial.xyz[f - 1][activeIdx], q = trial.xyz[f][activeIdx];
      if (valid(p) && valid(q)) line(p, q, trailColor, 1.5, targetCtx, w, h);
    }
  }

  // Distance line between Marker A and B (optional toggle)
  if (showDistance && valid(pts[a]) && valid(pts[b])) {
    const distColor = isLight ? "#b45309" : "#f2c875";
    line(pts[a], pts[b], distColor, 2, targetCtx, w, h);
  }

  // Render Marker Points with custom size and custom/palette color
  const visible = pts.map((p, i) => ({ p, i })).filter(v => valid(v.p)).map(v => ({ ...v, q: project(v.p, w, h) })).sort((a, b) => b.q[2] - a.q[2]);

  const actColor = isLight ? "#0f766e" : "#59dec3";
  const bColor = isLight ? "#b45309" : "#f2c875";
  const themeDefaultColor = isLight ? "#475569" : "#9bbed7";
  const regularColor = markerColor === "auto" ? themeDefaultColor : markerColor;

  const baseRadius = markerSize;
  for (const { i, q } of visible) {
    const isAct = i === activeIdx;
    const isA = showDistance && i === a, isB = showDistance && i === b;
    targetCtx.beginPath();
    const radius = isAct ? Math.max(3, baseRadius * 1.7) : (isA || isB ? Math.max(2.5, baseRadius * 1.4) : baseRadius);
    targetCtx.arc(q[0], q[1], radius, 0, Math.PI * 2);
    targetCtx.fillStyle = isAct ? actColor : (isA ? actColor : (isB ? bColor : regularColor));
    targetCtx.fill();

    if (isAct) {
      targetCtx.strokeStyle = isLight ? "#0f172a" : "#ffffff";
      targetCtx.lineWidth = Math.max(1.5, baseRadius * 0.4);
      targetCtx.stroke();
    }

    if ($("labels") && $("labels").checked) {
      targetCtx.fillStyle = isAct
        ? (isLight ? "#0f172a" : "#ffffff")
        : (isLight ? "#475569" : "#adbdcd");
      targetCtx.font = (isAct ? "bold 11px" : "10px") + " system-ui, sans-serif";
      targetCtx.fillText(trial.labels[i], q[0] + radius + 3, q[1] - 3);
    }
  }
}

// 3D Scene Rendering
function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (w > 0 && h > 0) {
    drawSceneToContext(ctx, w, h);
  }
  if (!trial) return;

  // Update Frame readout & timeline slider
  const curTime = (frame / trial.rate_hz).toFixed(3);
  const totalTime = ((trial.xyz.length - 1) / trial.rate_hz).toFixed(3);
  $("frame").textContent = `${frame + 1} / ${trial.xyz.length} · ${curTime} s / ${totalTime} s`;
  $("timeline").value = String(frame);

  // Update distance readout
  const d = distances[frame];
  if ($("distance")) {
    if (!showDistance) {
      $("distance").textContent = Number.isFinite(d) ? `${d.toFixed(4)} m (Oculto)` : "Oculto";
      $("distance").style.opacity = "0.55";
    } else {
      $("distance").textContent = Number.isFinite(d) ? `${d.toFixed(4)} m` : "Missing";
      $("distance").style.opacity = "1";
    }
  }

  // Draw charts and update table
  drawPlot1();
  drawPlot2();
  updateTable();

  // Synchronize any popped out subwindows
  syncPopoutContent("panel-plot1");
  syncPopoutContent("panel-plot2");
  syncPopoutContent("panel-table");
  syncPopoutContent("panel-3d");
}

// Plot caching to avoid expensive calculations every animation frame
let cachedPlot1Data = null;
let cachedPlot1Mode = "";
let cachedPlot1Marker = -1;

function drawPlot1() {
  const canvasG = graph1;
  const gx = gx1;
  const mode = $("plot1-mode") ? $("plot1-mode").value : "distance";
  drawSinglePlot(canvasG, gx, mode, $("plot1-readout"), 1);
}

function drawPlot2() {
  if (!graph2 || !$("panel-plot2") || $("panel-plot2").hidden) return;
  const canvasG = $("graph2");
  const gx = graph2;
  const mode = $("plot2-mode") ? $("plot2-mode").value : "active-z";
  drawSinglePlot(canvasG, gx, mode, $("plot2-readout"), 2);
}

function drawPlots() {
  drawPlot1();
  drawPlot2();
}

function getSeriesForMode(mode) {
  const isLight = currentTheme === "light";
  const colDistance = isLight ? "#b45309" : "#f2c875";
  const colZ = isLight ? "#0f766e" : "#59dec3";
  const colX = isLight ? "#dc2626" : "#ef8686";
  const colY = isLight ? "#16a34a" : "#82d99d";
  const colSpeed = isLight ? "#7c3aed" : "#a38bf5";

  const series = [];
  const totalFrames = trial.xyz.length;
  if (mode === "distance") {
    series.push({ name: "Distance", color: colDistance, values: distances });
  } else if (mode === "active-z") {
    const vals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
    series.push({ name: "Z (Height)", color: colZ, values: vals });
  } else if (mode === "active-xyz") {
    const xVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][0] : NaN);
    const yVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][1] : NaN);
    const zVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
    series.push({ name: "X", color: colX, values: xVals });
    series.push({ name: "Y", color: colY, values: yVals });
    series.push({ name: "Z", color: colZ, values: zVals });
  } else if (mode === "active-speed") {
    const speedVals = [0];
    for (let i = 1; i < totalFrames; i++) {
      const p = trial.xyz[i - 1][activeMarkerIndex], q = trial.xyz[i][activeMarkerIndex];
      if (valid(p) && valid(q)) {
        speedVals.push(Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]) * trial.rate_hz);
      } else {
        speedVals.push(NaN);
      }
    }
    series.push({ name: "Speed (m/s)", color: colSpeed, values: speedVals });
  } else if (mode === "fp-all-fz" && trial.force_plates && trial.force_plates.length) {
    const fpPalette = isLight
      ? ["#ea580c", "#2563eb", "#059669", "#7c3aed"]
      : ["#f97316", "#60a5fa", "#34d399", "#a78bfa"];
    const totalFzVals = new Array(totalFrames).fill(0);
    trial.force_plates.forEach((fp, idx) => {
      const col = fpPalette[idx % fpPalette.length];
      const vals = fp.force.map(f => f ? f[2] : 0);
      series.push({ name: `${fp.name} Fz (N)`, color: col, values: vals });
      for (let i = 0; i < totalFrames; i++) {
        if (Number.isFinite(vals[i])) totalFzVals[i] += vals[i];
      }
    });
    series.unshift({
      name: "Total Vertical GRF (N)",
      color: isLight ? "#dc2626" : "#ef4444",
      values: totalFzVals,
    });
  } else if (mode.startsWith("fp-plate-") && trial.force_plates) {
    const pIdx = Number(mode.replace("fp-plate-", ""));
    const fp = trial.force_plates[pIdx];
    if (fp && fp.force) {
      const colX = isLight ? "#dc2626" : "#ef8686";
      const colY = isLight ? "#16a34a" : "#82d99d";
      const colZ = isLight ? "#2563eb" : "#60a5fa";
      series.push({ name: `${fp.name} Fx (N)`, color: colX, values: fp.force.map(f => f ? f[0] : 0) });
      series.push({ name: `${fp.name} Fy (N)`, color: colY, values: fp.force.map(f => f ? f[1] : 0) });
      series.push({ name: `${fp.name} Fz (N)`, color: colZ, values: fp.force.map(f => f ? f[2] : 0) });
    }
  } else if (mode === "fp-cop" && trial.force_plates) {
    const copPalette = isLight
      ? [["#b45309", "#d97706"], ["#1d4ed8", "#3b82f6"]]
      : [["#f59e0b", "#fbbf24"], ["#60a5fa", "#93c5fd"]];
    trial.force_plates.forEach((fp, idx) => {
      const cols = copPalette[idx % copPalette.length];
      const copX = fp.cop.map(p => p && Number.isFinite(p[0]) ? p[0] : NaN);
      const copY = fp.cop.map(p => p && Number.isFinite(p[1]) ? p[1] : NaN);
      series.push({ name: `${fp.name} COP X (m)`, color: cols[0], values: copX });
      series.push({ name: `${fp.name} COP Y (m)`, color: cols[1], values: copY });
    });
  }
  return series;
}

function drawSinglePlot(canvasG, gx, mode, readoutEl, plotId) {
  const w = canvasG.clientWidth, h = canvasG.clientHeight;
  gx.clearRect(0, 0, w, h);
  if (!trial) return;

  const isLight = currentTheme === "light";
  const series = getSeriesForMode(mode);
  let lo = Infinity, hi = -Infinity;
  for (const s of series) {
    for (const v of s.values) {
      if (Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  }

  const isPlot1 = plotId === 1 || plotId === "panel-plot1";
  const hasPreview = isPlot1 && filterPreviewActive && filterPreviewSeries && Array.isArray(filterPreviewSeries.values);
  if (hasPreview) {
    for (const v of filterPreviewSeries.values) {
      if (Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  }

  if (!Number.isFinite(lo)) return;
  const extent = Math.max(hi - lo, 0.001);
  const totalFrames = trial.xyz.length;

  if (readoutEl) {
    let curVals = series.map(s => {
      const v = s.values[frame];
      return `${s.name}: ${Number.isFinite(v) ? v.toFixed(3) : "—"}`;
    }).join("  |  ");
    if (hasPreview) {
      const pv = filterPreviewSeries.values[frame];
      curVals += `  |  [Preview: ${Number.isFinite(pv) ? pv.toFixed(3) : "—"}]`;
    }
    readoutEl.textContent = curVals;
  }

  gx.strokeStyle = isLight ? "rgba(0, 0, 0, 0.08)" : "rgba(255, 255, 255, 0.08)";
  gx.lineWidth = 1;
  for (let k = 0; k <= 3; k++) {
    const y = 14 + k * (h - 28) / 3;
    gx.beginPath();
    gx.moveTo(50, y);
    gx.lineTo(w - 10, y);
    gx.stroke();
  }

  for (const s of series) {
    gx.strokeStyle = s.color;
    gx.lineWidth = 1.5;
    gx.beginPath();
    let started = false;
    s.values.forEach((d, i) => {
      if (!Number.isFinite(d)) {
        started = false;
        return;
      }
      const x = 50 + i * (w - 65) / Math.max(1, totalFrames - 1);
      const y = h - 16 - (d - lo) * (h - 34) / extent;
      if (started) gx.lineTo(x, y);
      else gx.moveTo(x, y);
      started = true;
    });
    gx.stroke();
  }

  // Overlay Live Filter Preview series as dashed line
  if (hasPreview) {
    gx.save();
    gx.strokeStyle = isLight ? "#ea580c" : "#38bdf8";
    gx.lineWidth = 2.0;
    gx.setLineDash([5, 3]);
    gx.beginPath();
    let started = false;
    filterPreviewSeries.values.forEach((d, i) => {
      if (!Number.isFinite(d)) {
        started = false;
        return;
      }
      const x = 50 + i * (w - 65) / Math.max(1, totalFrames - 1);
      const y = h - 16 - (d - lo) * (h - 34) / extent;
      if (started) gx.lineTo(x, y);
      else gx.moveTo(x, y);
      started = true;
    });
    gx.stroke();
    gx.restore();
  }

  gx.fillStyle = isLight ? "#64748b" : "#8298ad";
  gx.font = "10px system-ui, sans-serif";
  gx.fillText(`${hi.toFixed(3)}`, 2, 14);
  gx.fillText(`${lo.toFixed(3)}`, 2, h - 10);

  const curX = 50 + frame * (w - 65) / Math.max(1, totalFrames - 1);
  gx.strokeStyle = isLight ? "#b45309" : "#f2c875";
  gx.lineWidth = 1.5;
  gx.beginPath();
  gx.moveTo(curX, 0);
  gx.lineTo(curX, h);
  gx.stroke();
}

function updateTable() {
  if (!$("panel-table") || $("panel-table").hidden || !trial) return;
  const tbody = $("marker-table-body");
  if (!tbody) return;
  const pts = trial.xyz[frame] || [];
  const isLight = currentTheme === "light";
  const okColor = isLight ? "#0f766e" : "#59dec3";
  const errColor = isLight ? "#dc2626" : "#ef8686";

  for (let i = 0; i < trial.labels.length; i++) {
    const row = tbody.children[i];
    if (!row) continue;
    const p = pts[i];
    const isOk = valid(p);
    row.classList.toggle("selected", i === activeMarkerIndex);
    row.cells[2].textContent = isOk ? "OK" : "Missing";
    row.cells[2].style.color = isOk ? okColor : errColor;
    row.cells[3].textContent = isOk ? p[0].toFixed(3) : "—";
    row.cells[4].textContent = isOk ? p[1].toFixed(3) : "—";
    row.cells[5].textContent = isOk ? p[2].toFixed(3) : "—";
  }
}

function buildTable() {
  const tbody = $("marker-table-body");
  if (!tbody || !trial) return;
  tbody.replaceChildren(...trial.labels.map((lbl, i) => {
    const tr = document.createElement("tr");
    tr.onclick = () => selectActiveMarker(i);
    tr.innerHTML = `<td>${i + 1}</td><td><strong>${lbl}</strong></td><td>—</td><td>—</td><td>—</td><td>—</td>`;
    return tr;
  }));
}

function measure() {
  if (!trial) return;
  const a = Number($("marker-a").value), b = Number($("marker-b").value);
  distances = trial.xyz.map(p => valid(p[a]) && valid(p[b]) ? Math.hypot(...p[a].map((v, j) => v - p[b][j])) : NaN);
  draw();
  saveSessionState();
}

function pause() {
  playing = false;
  $("play").textContent = "Play";
  elapsed = 0;
}

function selectActiveMarker(idx) {
  activeMarkerIndex = idx;
  if ($("marker-select")) $("marker-select").value = String(idx);
  draw();
  saveSessionState();
}

function seekToMotion() {
  if (!trial) return;
  pause();
  let motionFrame = 0;
  const pts0 = trial.xyz[0];
  for (let f = 1; f < trial.xyz.length; f++) {
    let diffSum = 0;
    for (let m = 0; m < trial.labels.length; m++) {
      const p = pts0[m], q = trial.xyz[f][m];
      if (valid(p) && valid(q)) diffSum += Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
    }
    if (diffSum / trial.labels.length > 0.04) {
      motionFrame = Math.max(0, f - 10);
      break;
    }
  }
  frame = motionFrame;
  draw();
  saveSessionState();
  status(`Jumped to motion onset at frame ${frame + 1} (${(frame / trial.rate_hz).toFixed(2)}s).`);
}

function saveSessionState() {
  if (!trial) return;
  try {
    const state = {
      trialName: trial.name,
      frame,
      activeMarkerIndex,
      markerA: $("marker-a") ? $("marker-a").value : "0",
      markerB: $("marker-b") ? $("marker-b").value : "1",
      activeSkeletonTemplate,
      yaw, pitch, zoom, pan,
      up: $("up") ? $("up").value : "z",
      grid: $("grid") ? $("grid").checked : true,
      labels: $("labels") ? $("labels").checked : true,
      trail: $("trail") ? $("trail").checked : true,
      bones: $("bones") ? $("bones").checked : true,
      loop: $("loop") ? $("loop").checked : true,
      showDistance,
      showForcePlates,
      showForceVectors,
      forceVectorScale,
      forceThreshold,
      speed: $("speed") ? $("speed").value : "1",
      theme: currentTheme,
      markerSize,
      markerColor,
      currentLCS,
      activeFilterConfig,
      plotHeight: $("windows-container") ? getComputedStyle($("windows-container")).getPropertyValue("--plot-height").trim() : "170px"
    };
    sessionStorage.setItem("mkvis3d_session", JSON.stringify(state));
  } catch (e) {
    // Ignore quota errors
  }
}

function restoreSessionState(data) {
  try {
    const raw = sessionStorage.getItem("mkvis3d_session");
    if (!raw) return;
    const state = JSON.parse(raw);
    if (!state || state.trialName !== data.name) return;

    if (state.currentLCS && typeof state.currentLCS === "object" && state.currentLCS.ap && state.currentLCS.axial) {
      currentLCS = state.currentLCS;
    }
    if (state.activeFilterConfig && typeof state.activeFilterConfig === "object") {
      activeFilterConfig = state.activeFilterConfig;
    }

    if (Number.isFinite(state.frame) && state.frame >= 0 && state.frame < data.xyz.length) {
      frame = state.frame;
    }
    if (Number.isFinite(state.activeMarkerIndex)) {
      activeMarkerIndex = state.activeMarkerIndex;
      if ($("marker-select")) $("marker-select").value = String(activeMarkerIndex);
    }
    if (state.markerA && $("marker-a")) $("marker-a").value = state.markerA;
    if (state.markerB && $("marker-b")) $("marker-b").value = state.markerB;
    if (Number.isFinite(state.yaw)) yaw = state.yaw;
    if (Number.isFinite(state.pitch)) pitch = state.pitch;
    if (Number.isFinite(state.zoom)) zoom = state.zoom;
    if (Array.isArray(state.pan)) pan = state.pan;
    if (state.up && $("up")) $("up").value = state.up;
    if (typeof state.grid === "boolean" && $("grid")) $("grid").checked = state.grid;
    if (typeof state.labels === "boolean" && $("labels")) $("labels").checked = state.labels;
    if (typeof state.trail === "boolean" && $("trail")) $("trail").checked = state.trail;
    if (typeof state.bones === "boolean" && $("bones")) $("bones").checked = state.bones;
    if (typeof state.loop === "boolean" && $("loop")) $("loop").checked = state.loop;
    if (typeof state.showDistance === "boolean") setDistanceVisible(state.showDistance);
    if (typeof state.showForcePlates === "boolean") {
      showForcePlates = state.showForcePlates;
      if ($("show-force-plates")) $("show-force-plates").checked = showForcePlates;
    }
    if (typeof state.showForceVectors === "boolean") {
      showForceVectors = state.showForceVectors;
      if ($("show-force-vectors")) $("show-force-vectors").checked = showForceVectors;
    }
    if (Number.isFinite(state.forceVectorScale)) {
      forceVectorScale = state.forceVectorScale;
      if ($("force-scale-slider")) $("force-scale-slider").value = String((forceVectorScale * 1000).toFixed(1));
      if ($("force-scale-val")) $("force-scale-val").textContent = `${(forceVectorScale * 1000).toFixed(1)} mm/N`;
    }
    if (Number.isFinite(state.forceThreshold)) {
      forceThreshold = state.forceThreshold;
      if ($("force-threshold-slider")) $("force-threshold-slider").value = String(forceThreshold);
      if ($("force-threshold-val")) $("force-threshold-val").textContent = `${forceThreshold} N`;
    }
    if (state.speed && $("speed")) $("speed").value = state.speed;
    if (state.theme && (state.theme === "light" || state.theme === "dark")) {
      setTheme(state.theme);
    }
    if (Number.isFinite(state.markerSize)) {
      setMarkerSize(state.markerSize);
    }
    if (typeof state.markerColor === "string") {
      setMarkerColor(state.markerColor);
    }
    if (state.plotHeight && $("windows-container")) {
      $("windows-container").style.setProperty("--plot-height", state.plotHeight);
    }

    if (state.activeSkeletonTemplate && state.activeSkeletonTemplate !== "none") {
      if ($("skeleton-template-select")) $("skeleton-template-select").value = state.activeSkeletonTemplate;
      if (state.activeSkeletonTemplate === "vicon_squat") {
        applySkeletonTemplate(VICON_SQUAT_TEMPLATE);
      } else if (embeddedTemplates[state.activeSkeletonTemplate]) {
        applySkeletonTemplate(embeddedTemplates[state.activeSkeletonTemplate]);
      }
    }
  } catch (e) {
    console.warn("Could not restore session state:", e);
  }
}

function load(data) {
  trial = data;
  frame = 0;
  pause();
  activeMarkerIndex = 0;
  skeletonPairs = [];

  // Deep copy raw coordinates for lossless LCS and filter transformations
  rawLoadedXYZ = data.xyz.map(f => f.map(p => p ? [p[0], p[1], p[2]] : null));
  currentLCS = { ap: "+Y", axial: "+Z" };
  activeFilterConfig = null;
  filterPreviewActive = false;
  filterPreviewSeries = null;

  $("title").textContent = data.name;
  $("meta").textContent = `${data.xyz.length} frames · ${data.labels.length} markers · ${data.rate_hz} Hz · coordinates in meters`;
  if ($("marker-count-badge")) $("marker-count-badge").textContent = `${data.labels.length} markers`;
  $("welcome").hidden = true;

  for (const key of ["marker-a", "marker-b", "marker-select"]) {
    if (!$(key)) continue;
    $(key).replaceChildren(...data.labels.map((label, i) => {
      const o = document.createElement("option");
      o.value = String(i);
      o.textContent = label;
      return o;
    }));
  }
  if ($("marker-b")) $("marker-b").value = String(Math.min(1, data.labels.length - 1));

  for (const id of ["play", "prev", "next", "timeline", "export", "snapshot", "first", "last", "seek-motion", "btn-load-skeleton", "btn-clear-skeleton"]) {
    if ($(id)) $(id).disabled = false;
  }
  $("timeline").max = String(data.xyz.length - 1);

  initSkeleton(data.labels);
  buildTable();

  // Handle Force Plates
  rawForcePlates = data.force_plates ? JSON.parse(JSON.stringify(data.force_plates)) : null;
  const hasForcePlates = Array.isArray(data.force_plates) && data.force_plates.length > 0;
  if ($("force-platforms-section")) {
    $("force-platforms-section").hidden = !hasForcePlates;
    if (hasForcePlates && $("force-plate-count-badge")) {
      $("force-plate-count-badge").textContent = `${data.force_plates.length} plates`;
    }
  }

  // Update plot modes dropdowns with force plate options if present
  for (const plotSelectId of ["plot1-mode", "plot2-mode"]) {
    const sel = $(plotSelectId);
    if (!sel) continue;
    Array.from(sel.querySelectorAll(".fp-opt-group, option[value^='fp-']")).forEach(opt => opt.remove());
    if (hasForcePlates) {
      const optGroup = document.createElement("optgroup");
      optGroup.label = "── Force Plates & GRF ──";
      optGroup.className = "fp-opt-group";

      const optFz = document.createElement("option");
      optFz.value = "fp-all-fz";
      optFz.textContent = "Ground Reaction Force · Vertical (Fz - Total & Plates)";
      optGroup.appendChild(optFz);

      data.force_plates.forEach((fp, idx) => {
        const optP = document.createElement("option");
        optP.value = `fp-plate-${idx}`;
        optP.textContent = `${fp.name} · 3D Forces (Fx, Fy, Fz)`;
        optGroup.appendChild(optP);
      });

      const optCop = document.createElement("option");
      optCop.value = "fp-cop";
      optCop.textContent = "Center of Pressure · (COP X & Y)";
      optGroup.appendChild(optCop);

      sel.appendChild(optGroup);
    }
  }
  if (hasForcePlates && $("plot1-mode")) {
    $("plot1-mode").value = "fp-all-fz";
  }

  fit();
  measure();
  restoreSessionState(data);
  if (currentLCS.ap !== "+Y" || currentLCS.axial !== "+Z" || activeFilterConfig) {
    recomputeTrialXYZ();
  }
  updateLCSUI();
  updateFilterUI();
  saveSessionState();
  status("File loaded. Coordinates in meters; missing frames are preserved.");
}

function resize() {
  for (const c of [canvas, graph1, $("graph2")]) {
    if (!c) continue;
    const ratio = window.devicePixelRatio || 1;
    c.width = Math.round(c.clientWidth * ratio);
    c.height = Math.round(c.clientHeight * ratio);
    c.getContext("2d").setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  draw();
}
new ResizeObserver(resize).observe($("workspace"));

// Transport & Playback
$("play").onclick = () => {
  if (!trial) return;
  if (playing) pause();
  else {
    if (frame >= trial.xyz.length - 1) frame = 0;
    playing = true;
    lastTick = performance.now();
    $("play").textContent = "Pause";
  }
};

function step(delta) {
  if (!trial) return;
  pause();
  frame = Math.max(0, Math.min(trial.xyz.length - 1, frame + delta));
  draw();
  saveSessionState();
}
$("prev").onclick = () => step(-1);
$("next").onclick = () => step(1);
if ($("first")) $("first").onclick = () => { pause(); frame = 0; draw(); saveSessionState(); };
if ($("last")) $("last").onclick = () => { pause(); frame = trial.xyz.length - 1; draw(); saveSessionState(); };
if ($("seek-motion")) $("seek-motion").onclick = seekToMotion;

$("timeline").oninput = () => {
  pause();
  frame = Number($("timeline").value);
  draw();
  saveSessionState();
};

function tick(now) {
  try {
    if (playing && trial) {
      elapsed += (now - lastTick) / 1000 * trial.rate_hz * Number($("speed").value);
      const advance = Math.floor(elapsed);
      elapsed -= advance;
      if (advance) {
        frame += advance;
        if (frame >= trial.xyz.length) {
          if ($("loop") && $("loop").checked) {
            frame %= trial.xyz.length;
          } else {
            frame = trial.xyz.length - 1;
            pause();
          }
        }
        draw();
      }
    }
  } catch (err) {
    console.error("Render loop error:", err);
  } finally {
    lastTick = now;
    requestAnimationFrame(tick);
  }
}
requestAnimationFrame(tick);

// Interactive 3D Orbit & Pan
let drag = null;
canvas.onpointerdown = e => {
  drag = [e.clientX, e.clientY];
  canvas.setPointerCapture(e.pointerId);
};
canvas.onpointermove = e => {
  if (!drag) return;
  const dx = e.clientX - drag[0], dy = e.clientY - drag[1];
  if (e.shiftKey) {
    pan[0] += dx;
    pan[1] += dy;
  } else {
    yaw += dx * 0.008;
    pitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, pitch + dy * 0.008));
  }
  drag = [e.clientX, e.clientY];
  draw();
  saveSessionState();
};
canvas.onpointerup = () => drag = null;
canvas.onpointercancel = () => drag = null;
canvas.onwheel = e => {
  e.preventDefault();
  zoom = Math.max(0.1, Math.min(20, zoom * Math.exp(-e.deltaY * 0.001)));
  draw();
  saveSessionState();
};

// Interactive Chart Click-to-Seek
function setupChartSeek(canvasEl) {
  if (!canvasEl) return;
  canvasEl.onclick = e => {
    if (!trial) return;
    const rect = canvasEl.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const usableW = canvasEl.clientWidth - 65;
    const norm = Math.max(0, Math.min(1, (clickX - 50) / usableW));
    pause();
    frame = Math.round(norm * (trial.xyz.length - 1));
    draw();
    saveSessionState();
  };
}
setupChartSeek(graph1);
if ($("graph2")) setupChartSeek($("graph2"));

// Camera View Presets
$("front").onclick = () => { yaw = 0; pitch = 0; draw(); saveSessionState(); };
$("side").onclick = () => { yaw = Math.PI / 2; pitch = 0; draw(); saveSessionState(); };
$("top").onclick = () => { yaw = 0; pitch = Math.PI / 2; draw(); saveSessionState(); };
$("reset").onclick = () => { fit(); saveSessionState(); };

if ($("up")) $("up").onchange = () => { fit(); saveSessionState(); };
for (const id of ["labels", "trail", "grid", "bones", "loop"]) {
  if ($(id)) $(id).onchange = () => { draw(); saveSessionState(); };
}
if ($("speed")) $("speed").onchange = saveSessionState;
for (const id of ["marker-a", "marker-b"]) {
  if ($(id)) $(id).onchange = measure;
}
if ($("marker-select")) {
  $("marker-select").onchange = () => selectActiveMarker(Number($("marker-select").value));
}
if ($("plot1-mode")) $("plot1-mode").onchange = draw;
if ($("plot2-mode")) $("plot2-mode").onchange = draw;

if ($("show-force-plates")) {
  $("show-force-plates").onchange = e => {
    showForcePlates = e.target.checked;
    draw();
    saveSessionState();
  };
}
if ($("show-force-vectors")) {
  $("show-force-vectors").onchange = e => {
    showForceVectors = e.target.checked;
    draw();
    saveSessionState();
  };
}
if ($("force-scale-slider")) {
  $("force-scale-slider").oninput = e => {
    const val = Number(e.target.value);
    forceVectorScale = val * 0.001;
    if ($("force-scale-val")) $("force-scale-val").textContent = `${val.toFixed(1)} mm/N`;
    draw();
  };
  $("force-scale-slider").onchange = saveSessionState;
}
if ($("force-threshold-slider")) {
  $("force-threshold-slider").oninput = e => {
    const val = Number(e.target.value);
    forceThreshold = val;
    if ($("force-threshold-val")) $("force-threshold-val").textContent = `${val} N`;
    draw();
  };
  $("force-threshold-slider").onchange = saveSessionState;
}

// Layout Presets
function setLayout(name) {
  const container = $("windows-container");
  container.className = `layout-${name}`;
  const splitter = $("vertical-splitter");
  if (name === "dual") {
    $("panel-plot2").hidden = false;
    $("panel-table").hidden = true;
    if (splitter) splitter.hidden = false;
  } else if (name === "full") {
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = false;
    if (splitter) splitter.hidden = false;
  } else if (name === "3d") {
    $("panel-plot1").hidden = true;
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = true;
    if (splitter) splitter.hidden = true;
  } else {
    $("panel-plot1").hidden = false;
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = true;
    if (splitter) splitter.hidden = false;
  }
  resize();
}
if ($("preset-default")) $("preset-default").onclick = () => setLayout("default");
if ($("preset-dual")) $("preset-dual").onclick = () => setLayout("dual");
if ($("preset-full")) $("preset-full").onclick = () => setLayout("full");
if ($("preset-3d")) $("preset-3d").onclick = () => setLayout("3d");

if ($("btn-close-plot2")) $("btn-close-plot2").onclick = () => setLayout("default");
if ($("btn-close-table")) $("btn-close-table").onclick = () => setLayout("default");

// Skeleton Template Loading
async function loadSelectedSkeleton() {
  if (!trial) {
    status("Carregue um arquivo antes de carregar o skeleton.", true);
    return;
  }
  const select = $("skeleton-template-select");
  const val = select ? select.value : "none";
  if (val === "none") {
    skeletonPairs = [];
    activeSkeletonTemplate = "none";
    if ($("skeleton-status-badge")) {
      $("skeleton-status-badge").textContent = "Nenhum";
      $("skeleton-status-badge").style.color = "var(--text-muted)";
    }
    draw();
    saveSessionState();
    status("Nenhum modelo de skeleton selecionado.");
    return;
  }
  if (val === "custom") {
    if (loadedCustomTemplate) {
      activeSkeletonTemplate = "custom";
      const count = applySkeletonTemplate(loadedCustomTemplate);
      saveSessionState();
      status(`Skeleton personalizado carregado (${count} conexões).`);
    } else {
      if ($("file-skeleton-custom")) $("file-skeleton-custom").click();
    }
    return;
  }
  if (val === "vicon_squat") {
    activeSkeletonTemplate = "vicon_squat";
    const count = applySkeletonTemplate(VICON_SQUAT_TEMPLATE);
    saveSessionState();
    status(`Skeleton Vicon Squat carregado (${count} conexões).`);
    return;
  }

  let tObj = embeddedTemplates[val];
  if (!tObj && boot.server) {
    try {
      const resp = await fetch(`/api/skeleton_template?name=${encodeURIComponent(val)}`);
      if (resp.ok) tObj = await resp.json();
    } catch (e) {
      console.warn("Could not fetch skeleton template:", e);
    }
  }

  if (tObj) {
    activeSkeletonTemplate = val;
    const count = applySkeletonTemplate(tObj);
    saveSessionState();
    status(`Skeleton ${tObj.schema || val} carregado (${count} conexões).`);
  } else {
    status(`Template '${val}' não encontrado.`, true);
  }
}

if ($("btn-load-skeleton")) $("btn-load-skeleton").onclick = loadSelectedSkeleton;
if ($("btn-clear-skeleton")) {
  $("btn-clear-skeleton").onclick = () => {
    skeletonPairs = [];
    activeSkeletonTemplate = "none";
    if ($("skeleton-template-select")) $("skeleton-template-select").value = "none";
    if ($("skeleton-status-badge")) {
      $("skeleton-status-badge").textContent = "No skeleton";
      $("skeleton-status-badge").style.color = "var(--text-muted)";
    }
    saveSessionState();
    draw();
    status("Skeleton limpo.");
  };
}

if ($("file-skeleton-custom")) {
  $("file-skeleton-custom").onchange = e => {
    const f = e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = evt => {
      try {
        const json = JSON.parse(evt.target.result);
        loadedCustomTemplate = json;
        activeSkeletonTemplate = "custom";
        if ($("skeleton-template-select")) $("skeleton-template-select").value = "custom";
        const count = applySkeletonTemplate(json);
        saveSessionState();
        status(`Template '${f.name}' carregado (${count} conexões).`);
      } catch (err) {
        status("Arquivo JSON inválido para skeleton.", true);
      }
    };
    reader.readAsText(f);
  };
}

// Menu Bar Interactivity
document.querySelectorAll(".menu-item").forEach(item => {
  const btn = item.querySelector(".menu-btn");
  btn.onclick = e => {
    e.stopPropagation();
    const isOpen = item.classList.contains("open");
    document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("open"));
    if (!isOpen) item.classList.add("open");
  };
});
document.addEventListener("click", () => {
  document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("open"));
});

// File Menu Actions
if ($("action-open-file")) $("action-open-file").onclick = () => $("file").click();
if ($("action-export-plot")) $("action-export-plot").onclick = () => $("export").click();
if ($("action-export-html")) $("action-export-html").onclick = () => $("snapshot").click();

if ($("action-export-all-csv")) {
  $("action-export-all-csv").onclick = () => {
    if (!trial) return;
    const header = ["frame", "time_s"];
    trial.labels.forEach(lbl => {
      header.push(`${lbl}_x`, `${lbl}_y`, `${lbl}_z`);
    });
    const rows = [header.join(",")];
    trial.xyz.forEach((framePts, f) => {
      const row = [f, (f / trial.rate_hz).toFixed(5)];
      framePts.forEach(pt => {
        if (valid(pt)) row.push(pt[0], pt[1], pt[2]);
        else row.push("", "", "");
      });
      rows.push(row.join(","));
    });
    download(rows.join("\n") + "\n", `${trial.name}_trajectories.csv`, "text/csv");
  };
}

// Sample file loaders
document.querySelectorAll("[data-example]").forEach(item => {
  item.onclick = async () => {
    const filename = item.dataset.example;
    pause();
    status(`Loading sample ${filename}...`);
    try {
      const resp = await fetch(`/api/example?name=${encodeURIComponent(filename)}`);
      if (!resp.ok) throw new Error("Could not load example from server.");
      const data = await resp.json();
      load(data);
    } catch (err) {
      status(err.message, true);
    }
  };
});

// View Menu Toggles
if ($("action-view-front")) $("action-view-front").onclick = () => $("front").click();
if ($("action-view-side")) $("action-view-side").onclick = () => $("side").click();
if ($("action-view-top")) $("action-view-top").onclick = () => $("top").click();
if ($("action-view-reset")) $("action-view-reset").onclick = () => $("reset").click();

function bindToggle(menuId, inputId) {
  const el = $(menuId), input = $(inputId);
  if (!el || !input) return;
  el.onclick = () => {
    input.checked = !input.checked;
    el.textContent = (input.checked ? "✓ " : "  ") + el.textContent.replace(/^[✓\s]+/, "");
    input.dispatchEvent(new Event("change"));
  };
}
bindToggle("action-toggle-grid", "grid");
bindToggle("action-toggle-labels", "labels");
bindToggle("action-toggle-trails", "trail");
bindToggle("action-toggle-bones", "bones");
bindToggle("action-toggle-loop", "loop");

// Theme toggles
if ($("btn-toggle-theme")) $("btn-toggle-theme").onclick = toggleTheme;
if ($("action-theme-dark")) $("action-theme-dark").onclick = () => setTheme("dark");
if ($("action-theme-light")) $("action-theme-light").onclick = () => setTheme("light");
if ($("action-opt-theme-dark")) $("action-opt-theme-dark").onclick = () => setTheme("dark");
if ($("action-opt-theme-light")) $("action-opt-theme-light").onclick = () => setTheme("light");

// Distance Measurement Toggle
function setDistanceVisible(visible) {
  showDistance = Boolean(visible);
  if ($("chk-show-distance")) $("chk-show-distance").checked = showDistance;
  if ($("txt-show-distance")) {
    $("txt-show-distance").textContent = showDistance ? "Exibir" : "Oculto";
    $("txt-show-distance").style.color = showDistance ? "var(--accent)" : "var(--text-muted)";
  }
  if ($("btn-toggle-distance")) {
    $("btn-toggle-distance").textContent = showDistance ? "Desativar" : "Ativar";
  }
  if ($("action-toggle-distance")) {
    $("action-toggle-distance").textContent = (showDistance ? "✓ " : "  ") + "Distance Line (A–B)  D";
  }
  saveSessionState();
  draw();
}

if ($("chk-show-distance")) {
  $("chk-show-distance").onchange = e => setDistanceVisible(e.target.checked);
}
if ($("btn-toggle-distance")) {
  $("btn-toggle-distance").onclick = () => setDistanceVisible(!showDistance);
}
if ($("action-toggle-distance")) {
  $("action-toggle-distance").onclick = () => setDistanceVisible(!showDistance);
}

// ==========================================
// Subwindows Floating & Pop-out Manager
// ==========================================
let activeFloatingPanes = new Set();
window.activeFloatingPanes = activeFloatingPanes;
window.floatPane = floatPane;
window.dockPane = dockPane;
window.dockAllPanes = dockAllPanes;
window.popoutPane = popoutPane;

function toggleFloatPane(paneId) {
  if (activeFloatingPanes.has(paneId)) {
    dockPane(paneId);
  } else {
    floatPane(paneId);
  }
}

function floatPane(paneId) {
  const pane = $(paneId);
  if (!pane) return;
  pane.hidden = false;
  pane.classList.add("floating-pane");
  activeFloatingPanes.add(paneId);

  if (!pane.style.top || pane.style.top === "0px") {
    const count = activeFloatingPanes.size;
    pane.style.top = `${80 + count * 35}px`;
    pane.style.left = `${340 + count * 35}px`;
  }

  const floatBtn = pane.querySelector(".btn-float");
  if (floatBtn) {
    floatBtn.textContent = "↙";
    floatBtn.title = "Fixar / Reanexar à grade";
  }
  initDraggablePane(pane);

  if (!pane._paneResizeObs) {
    pane._paneResizeObs = new ResizeObserver(() => {
      if (pane.classList.contains("floating-pane")) resize();
    });
    pane._paneResizeObs.observe(pane);
  }

  resize();
}

function dockPane(paneId) {
  const pane = $(paneId);
  if (!pane) return;
  pane.classList.remove("floating-pane");
  pane.style.top = "";
  pane.style.left = "";
  pane.style.width = "";
  pane.style.height = "";
  activeFloatingPanes.delete(paneId);

  const floatBtn = pane.querySelector(".btn-float");
  if (floatBtn) {
    floatBtn.textContent = "↗";
    floatBtn.title = "Janela Flutuante (Arrastável / Redimensionável)";
  }
  resize();
}

function dockAllPanes() {
  for (const paneId of Array.from(activeFloatingPanes)) {
    dockPane(paneId);
  }
  for (const paneId of Object.keys(popoutWindows)) {
    restorePoppedOutPane(paneId);
  }
}

function initDraggablePane(pane) {
  const header = pane.querySelector(".pane-header");
  if (!header || header.dataset.dragInit) return;
  header.dataset.dragInit = "true";

  let startX = 0, startY = 0, initialLeft = 0, initialTop = 0, dragging = false;

  header.addEventListener("pointerdown", e => {
    if (!pane.classList.contains("floating-pane")) return;
    if (["BUTTON", "SELECT", "INPUT"].includes(e.target.tagName)) return;
    dragging = true;
    pane.classList.add("is-dragging");
    startX = e.clientX;
    startY = e.clientY;
    const rect = pane.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;
    header.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  header.addEventListener("pointermove", e => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    const newLeft = Math.max(10, Math.min(window.innerWidth - 100, initialLeft + dx));
    const newTop = Math.max(10, Math.min(window.innerHeight - 60, initialTop + dy));
    pane.style.left = `${newLeft}px`;
    pane.style.top = `${newTop}px`;
  });

  const stopDrag = e => {
    if (dragging) {
      dragging = false;
      pane.classList.remove("is-dragging");
      try { header.releasePointerCapture(e.pointerId); } catch (_) {}
    }
  };
  header.addEventListener("pointerup", stopDrag);
  header.addEventListener("pointercancel", stopDrag);
}

function popoutPane(paneId) {
  if (activeFloatingPanes.has(paneId)) {
    dockPane(paneId);
  }
  const pane = $(paneId);
  if (!pane) return;

  if (popoutWindows[paneId] && !popoutWindows[paneId].closed) {
    popoutWindows[paneId].focus();
    return;
  }

  const titleText = pane.querySelector(".pane-title") ? pane.querySelector(".pane-title").innerText.replace(/^[●\s]+/, "") : paneId;

  const popWin = window.open("", `mkvis3d_popout_${paneId}`, "width=820,height=520,resizable=yes,scrollbars=yes");
  if (!popWin) {
    status("Pop-up bloqueado pelo navegador. Abrindo em janela flutuante interna.");
    floatPane(paneId);
    return;
  }

  popoutWindows[paneId] = popWin;

  const doc = popWin.document;
  doc.open();
  doc.write(`<!DOCTYPE html>
<html data-theme="${currentTheme}">
<head>
  <meta charset="utf-8">
  <title>mkvis3d — ${titleText}</title>
  <link rel="icon" href="/favicon.ico">
  <style>
    :root, [data-theme="dark"] {
      color-scheme: dark;
      --bg-dark: #0e151e; --bg-surface: #141f2d; --bg-panel: #111a24; --bg-panel-alt: #162231;
      --accent: #59dec3; --accent-hover: #7be4ce; --accent-text: #081a17;
      --text: #e4edf5; --text-muted: #8295a8; --border-color: rgba(255, 255, 255, 0.08);
      --input-bg: #0e151e; --btn-bg: #141f2d; --btn-hover-bg: #1a283a;
    }
    [data-theme="light"] {
      color-scheme: light;
      --bg-dark: #f0f4f8; --bg-surface: #e2e8f0; --bg-panel: #ffffff; --bg-panel-alt: #f8fafc;
      --accent: #0f766e; --accent-hover: #115e59; --accent-text: #ffffff;
      --text: #1e293b; --text-muted: #64748b; --border-color: #cbd5e1;
      --input-bg: #ffffff; --btn-bg: #ffffff; --btn-hover-bg: #e2e8f0;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg-dark); color: var(--text);
      display: flex; flex-direction: column; height: 100vh; overflow: hidden; user-select: none;
    }
    .pop-header {
      min-height: 40px; background: var(--bg-panel-alt); border-bottom: 1px solid var(--border-color);
      display: flex; align-items: center; justify-content: space-between; padding: 4px 12px;
      font-size: 12px; font-weight: 600; gap: 10px; flex-wrap: wrap;
    }
    .pop-header-left, .pop-header-center, .pop-header-right {
      display: flex; align-items: center; gap: 8px;
    }
    .pop-title { color: var(--text); font-weight: 700; white-space: nowrap; }
    .pop-select {
      background: var(--input-bg); color: var(--accent); border: 1px solid var(--border-color);
      border-radius: 4px; padding: 3px 6px; font-size: 11px; font-weight: 600; cursor: pointer;
    }
    .pop-tool-btn {
      background: var(--btn-bg); color: var(--text); border: 1px solid var(--border-color);
      border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 600; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
    }
    .pop-tool-btn:hover { border-color: var(--accent); color: var(--accent); }
    .pop-play-btn { background: var(--accent); color: var(--accent-text); border: none; }
    .pop-play-btn:hover { background: var(--accent-hover); color: var(--accent-text); }
    .pop-timeline-range {
      width: 140px; accent-color: var(--accent); cursor: pointer;
    }
    .pop-frame-badge {
      font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap;
    }
    .pop-readout-text {
      font-size: 11px; color: var(--accent); font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap;
    }
    .btn-redock {
      background: var(--btn-bg); color: var(--accent); border: 1px solid var(--border-color);
      border-radius: 4px; padding: 4px 10px; font-weight: 600; cursor: pointer; font-size: 11px; white-space: nowrap;
    }
    .btn-redock:hover { background: var(--accent); color: var(--accent-text); }
    .pop-body { flex: 1; position: relative; overflow: auto; display: flex; min-height: 0; }
    canvas { display: block; width: 100%; height: 100%; }
    .table-wrap { width: 100%; height: 100%; overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th, td { padding: 5px 8px; text-align: left; border-bottom: 1px solid var(--border-color); font-variant-numeric: tabular-nums; }
    th { background: var(--bg-panel-alt); position: sticky; top: 0; color: var(--text-muted); font-weight: 600; z-index: 1; }
    tr:hover { background: rgba(89, 222, 195, 0.08); cursor: pointer; }
    tr.selected { background: rgba(89, 222, 195, 0.2); font-weight: 600; color: var(--accent); }
  </style>
</head>
<body>
  <div class="pop-header">
    <div class="pop-header-left">
      <span class="pop-title">● ${titleText}</span>
      ${paneId === "panel-plot1" || paneId === "panel-plot2" ? `
        <select id="pop-plot-mode" class="pop-select" title="Modo do Gráfico">
          <option value="distance">Distance (Marker A to B)</option>
          <option value="active-z">Active Marker · Z Position (Height)</option>
          <option value="active-xyz">Active Marker · X, Y, Z Coordinates</option>
          <option value="active-speed">Active Marker · 3D Velocity / Speed</option>
        </select>
      ` : ""}
    </div>
    <div class="pop-header-center">
      <button id="pop-btn-prev" class="pop-tool-btn" title="Frame Anterior (←)">◀</button>
      <button id="pop-btn-play" class="pop-tool-btn pop-play-btn" title="Play / Pause (Space)">Play</button>
      <button id="pop-btn-next" class="pop-tool-btn" title="Próximo Frame (→)">▶</button>
      <input type="range" id="pop-timeline" class="pop-timeline-range" min="0" max="0" value="0" title="Scrub Timeline">
      <span id="pop-frame" class="pop-frame-badge">0 / 0</span>
    </div>
    <div class="pop-header-right">
      <span id="pop-readout" class="pop-readout-text"></span>
      <button class="btn-redock" id="btn-pop-redock">↙ Reanexar</button>
    </div>
  </div>
  <div class="pop-body" id="pop-body-container"></div>
</body>
</html>`);
  doc.close();

  const container = doc.getElementById("pop-body-container");
  if (paneId === "panel-plot1" || paneId === "panel-plot2") {
    const popCanvas = doc.createElement("canvas");
    popCanvas.id = "pop-canvas";
    popCanvas.className = "plot-canvas";
    popCanvas.style.cursor = "crosshair";
    container.appendChild(popCanvas);

    // Timeline scrubbing by clicking/dragging on the plot canvas in the popout window
    let isScrubbing = false;
    const seekFromPop = e => {
      if (!trial) return;
      const rect = popCanvas.getBoundingClientRect();
      const frac = Math.max(0, Math.min(1, (e.clientX - rect.left - 50) / Math.max(1, rect.width - 65)));
      pause();
      frame = Math.round(frac * (trial.xyz.length - 1));
      draw();
      saveSessionState();
    };
    popCanvas.addEventListener("pointerdown", e => {
      isScrubbing = true;
      seekFromPop(e);
      popCanvas.setPointerCapture(e.pointerId);
    });
    popCanvas.addEventListener("pointermove", e => {
      if (isScrubbing) seekFromPop(e);
    });
    const stopPopScrub = e => {
      if (isScrubbing) {
        isScrubbing = false;
        try { popCanvas.releasePointerCapture(e.pointerId); } catch (_) {}
      }
    };
    popCanvas.addEventListener("pointerup", stopPopScrub);
    popCanvas.addEventListener("pointercancel", stopPopScrub);

    // Link mode selector
    const popMode = doc.getElementById("pop-plot-mode");
    const origMode = paneId === "panel-plot1" ? $("plot1-mode") : $("plot2-mode");
    if (popMode && origMode) {
      popMode.value = origMode.value;
      popMode.onchange = () => {
        origMode.value = popMode.value;
        draw();
        saveSessionState();
      };
    }
  } else if (paneId === "panel-3d") {
    const pop3d = doc.createElement("canvas");
    pop3d.id = "pop-3d-canvas";
    pop3d.style.display = "block";
    pop3d.style.width = "100%";
    pop3d.style.height = "100%";
    pop3d.style.cursor = "grab";
    container.appendChild(pop3d);

    let isOrbit = false, isPan = false, pX = 0, pY = 0;
    pop3d.addEventListener("pointerdown", e => {
      isOrbit = e.button === 0 && !e.shiftKey;
      isPan = e.button === 1 || (e.button === 0 && e.shiftKey) || e.button === 2;
      pX = e.clientX; pY = e.clientY;
      pop3d.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    pop3d.addEventListener("pointermove", e => {
      if (!isOrbit && !isPan) return;
      const dx = e.clientX - pX, dy = e.clientY - pY;
      pX = e.clientX; pY = e.clientY;
      if (isOrbit) {
        yaw += dx * 0.008;
        pitch = Math.max(-1.5, Math.min(1.5, pitch - dy * 0.008));
      } else if (isPan) {
        pan[0] += dx * 0.002 * span / zoom;
        pan[1] -= dy * 0.002 * span / zoom;
      }
      draw();
    });
    const stop3d = e => {
      isOrbit = false; isPan = false;
      try { pop3d.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    pop3d.addEventListener("pointerup", stop3d);
    pop3d.addEventListener("pointercancel", stop3d);
    pop3d.addEventListener("wheel", e => {
      zoom = Math.max(0.1, Math.min(20, zoom * (e.deltaY > 0 ? 0.9 : 1.1)));
      draw();
      e.preventDefault();
    }, { passive: false });
  } else if (paneId === "panel-table") {
    const wrap = doc.createElement("div");
    wrap.className = "table-wrap";
    wrap.innerHTML = `
      <table class="marker-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Marker</th>
            <th>Status</th>
            <th>X (m)</th>
            <th>Y (m)</th>
            <th>Z (m)</th>
          </tr>
        </thead>
        <tbody id="pop-marker-table-body"></tbody>
      </table>
    `;
    container.appendChild(wrap);
  }

  // Transport controls in popout window
  const popPlay = doc.getElementById("pop-btn-play");
  if (popPlay) {
    popPlay.onclick = () => {
      if ($("play")) $("play").click();
    };
  }
  const popPrev = doc.getElementById("pop-btn-prev");
  if (popPrev) popPrev.onclick = () => step(-1);
  const popNext = doc.getElementById("pop-btn-next");
  if (popNext) popNext.onclick = () => step(1);
  const popTimeline = doc.getElementById("pop-timeline");
  if (popTimeline) {
    popTimeline.oninput = e => {
      if (!trial) return;
      pause();
      frame = Math.max(0, Math.min(trial.xyz.length - 1, Number(e.target.value)));
      draw();
      saveSessionState();
    };
  }

  // Keyboard navigation inside popout window
  popWin.addEventListener("keydown", e => {
    if (e.code === "Space") {
      e.preventDefault();
      if ($("play")) $("play").click();
    } else if (e.code === "ArrowLeft") {
      e.preventDefault();
      step(-1);
    } else if (e.code === "ArrowRight") {
      e.preventDefault();
      step(1);
    } else if (e.key === "c" || e.key === "C") {
      cycleMarkerColor();
    } else if (e.key === "+" || e.key === "=") {
      setMarkerSize(markerSize + 0.5);
    } else if (e.key === "-") {
      setMarkerSize(markerSize - 0.5);
    }
  });

  popWin.addEventListener("resize", () => {
    syncPopoutContent(paneId);
  });

  pane.classList.add("detached-pane");
  const origBody = pane.querySelector(".pane-body");
  let ph = pane.querySelector(".detached-placeholder");
  if (!ph) {
    ph = document.createElement("div");
    ph.className = "detached-placeholder";
    ph.id = `detached-ph-${paneId}`;
    ph.innerHTML = `
      <p><strong>${titleText}</strong> está destacada em uma janela independente.</p>
      <button type="button" onclick="restorePoppedOutPane('${paneId}')">↙ Reanexar</button>
    `;
    pane.appendChild(ph);
  }
  if (origBody) origBody.style.display = "none";

  const reDockBtn = doc.getElementById("btn-pop-redock");
  if (reDockBtn) {
    reDockBtn.onclick = () => {
      restorePoppedOutPane(paneId);
    };
  }

  popWin.onbeforeunload = () => {
    restorePoppedOutPane(paneId);
  };

  syncPopoutContent(paneId);
}

function restorePoppedOutPane(paneId) {
  const pane = $(paneId);
  if (!pane) return;
  pane.classList.remove("detached-pane");
  const ph = $(`detached-ph-${paneId}`);
  if (ph) ph.remove();
  const origBody = pane.querySelector(".pane-body");
  if (origBody) origBody.style.display = "";
  if (popoutWindows[paneId] && !popoutWindows[paneId].closed) {
    try { popoutWindows[paneId].close(); } catch (_) {}
  }
  delete popoutWindows[paneId];
  resize();
}

function syncPopoutContent(paneId) {
  const popWin = popoutWindows[paneId];
  if (!popWin || popWin.closed || !popWin.document) return;
  const doc = popWin.document;

  // Sync player transport
  if (trial) {
    const popTimeline = doc.getElementById("pop-timeline");
    if (popTimeline) {
      popTimeline.max = trial.xyz.length - 1;
      popTimeline.value = frame;
    }
    const popPlay = doc.getElementById("pop-btn-play");
    if (popPlay) {
      popPlay.textContent = playing ? "⏸ Pause" : "▶ Play";
    }
    const popFrame = doc.getElementById("pop-frame");
    if (popFrame) {
      const curTime = (frame / trial.rate_hz).toFixed(3);
      const totalTime = ((trial.xyz.length - 1) / trial.rate_hz).toFixed(3);
      popFrame.textContent = `${frame + 1} / ${trial.xyz.length} · ${curTime}s / ${totalTime}s`;
    }
  }

  if (paneId === "panel-plot1" || paneId === "panel-plot2") {
    const popCanvas = doc.getElementById("pop-canvas");
    const popReadout = doc.getElementById("pop-readout");
    const origModeEl = paneId === "panel-plot1" ? $("plot1-mode") : $("plot2-mode");
    const mode = origModeEl ? origModeEl.value : "distance";
    const popMode = doc.getElementById("pop-plot-mode");
    if (popMode && popMode.value !== mode) {
      popMode.value = mode;
    }
    if (popCanvas && popCanvas.parentElement) {
      const rect = popCanvas.parentElement.getBoundingClientRect();
      const ratio = popWin.devicePixelRatio || 1;
      if (rect.width > 0 && rect.height > 0) {
        if (popCanvas.width !== Math.round(rect.width * ratio) || popCanvas.height !== Math.round(rect.height * ratio)) {
          popCanvas.width = Math.round(rect.width * ratio);
          popCanvas.height = Math.round(rect.height * ratio);
        }
        const popCtx = popCanvas.getContext("2d");
        popCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
        drawSinglePlot(popCanvas, popCtx, mode, popReadout, paneId);
      }
    }
  } else if (paneId === "panel-3d") {
    const pop3d = doc.getElementById("pop-3d-canvas");
    if (pop3d && pop3d.parentElement && trial) {
      const rect = pop3d.parentElement.getBoundingClientRect();
      const ratio = popWin.devicePixelRatio || 1;
      if (rect.width > 0 && rect.height > 0) {
        if (pop3d.width !== Math.round(rect.width * ratio) || pop3d.height !== Math.round(rect.height * ratio)) {
          pop3d.width = Math.round(rect.width * ratio);
          pop3d.height = Math.round(rect.height * ratio);
        }
        const popCtx = pop3d.getContext("2d");
        popCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
        drawSceneToContext(popCtx, rect.width, rect.height);
      }
    }
  } else if (paneId === "panel-table") {
    const tbody = doc.getElementById("pop-marker-table-body");
    if (tbody && trial) {
      const pts = trial.xyz[frame] || [];
      const isLight = currentTheme === "light";
      const okColor = isLight ? "#0f766e" : "#59dec3";
      const errColor = isLight ? "#dc2626" : "#ef8686";
      if (tbody.children.length !== trial.labels.length) {
        tbody.innerHTML = "";
        for (let i = 0; i < trial.labels.length; i++) {
          const tr = doc.createElement("tr");
          tr.innerHTML = `<td>${i + 1}</td><td>${trial.labels[i]}</td><td></td><td></td><td></td><td></td>`;
          const mIdx = i;
          tr.onclick = () => selectActiveMarker(mIdx);
          tbody.appendChild(tr);
        }
      }
      for (let i = 0; i < trial.labels.length; i++) {
        const row = tbody.children[i];
        if (!row) continue;
        const p = pts[i];
        const isOk = valid(p);
        row.classList.toggle("selected", i === activeMarkerIndex);
        row.cells[2].textContent = isOk ? "OK" : "Missing";
        row.cells[2].style.color = isOk ? okColor : errColor;
        row.cells[3].textContent = isOk ? p[0].toFixed(3) : "—";
        row.cells[4].textContent = isOk ? p[1].toFixed(3) : "—";
        row.cells[5].textContent = isOk ? p[2].toFixed(3) : "—";
      }
    }
  }
}

// Attach listener to all btn-float and btn-popout buttons
document.querySelectorAll(".btn-float").forEach(btn => {
  btn.onclick = e => {
    e.stopPropagation();
    const paneId = btn.dataset.pane;
    if (paneId) toggleFloatPane(paneId);
  };
});

document.querySelectorAll(".btn-popout").forEach(btn => {
  btn.onclick = e => {
    e.stopPropagation();
    const paneId = btn.dataset.pane;
    if (paneId) popoutPane(paneId);
  };
});

if ($("action-float-plot1")) $("action-float-plot1").onclick = () => toggleFloatPane("panel-plot1");
if ($("action-popout-plot1")) $("action-popout-plot1").onclick = () => popoutPane("panel-plot1");
if ($("action-float-table")) $("action-float-table").onclick = () => toggleFloatPane("panel-table");
if ($("action-popout-table")) $("action-popout-table").onclick = () => popoutPane("panel-table");
if ($("action-dock-all")) $("action-dock-all").onclick = dockAllPanes;

// Blender and BVH exports
function exportBlenderPythonScript() {
  if (!trial) {
    status("Nenhum trial carregado para exportar para o Blender.", true);
    return;
  }
  status("Gerando script Python para o Blender...");
  const trialName = $("title") ? $("title").textContent.replace(/[^a-zA-Z0-9_-]/g, "_") : "trial";
  
  const bones = skeletonPairs.map(p => [trial.labels[p[0]], trial.labels[p[1]]]);
  
  const cleanXyz = trial.xyz.map(framePts =>
    framePts.map(pt => valid(pt) ? [Number(pt[0].toFixed(5)), Number(pt[1].toFixed(5)), Number(pt[2].toFixed(5))] : null)
  );

  const fps = Math.round(trial.rate_hz) || 100;
  const scriptContent = `# OpenBiomech (mkvis3d) -> Blender Generator Script
import bpy
import mathutils

def build_openbiomech():
    scene = bpy.context.scene
    scene.render.fps = ${fps}
    scene.frame_start = 1
    scene.frame_end = ${trial.xyz.length}
    scene.unit_settings.system = 'METRIC'
    
    coll_name = "OpenBiomech_${trialName}"
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll_name not in scene.collection.children:
        scene.collection.children.link(coll)
        
    labels = ${JSON.stringify(trial.labels)}
    trajectory = ${JSON.stringify(cleanXyz)}
    
    marker_objs = {}
    for idx, lbl in enumerate(labels):
        obj = bpy.data.objects.get(f"OB_{lbl}") or bpy.data.objects.new(f"OB_{lbl}", None)
        obj.empty_display_type = 'SPHERE'
        obj.empty_display_size = 0.015
        if f"OB_{lbl}" not in coll.objects:
            coll.objects.link(obj)
        marker_objs[lbl] = obj
        marker_objs[f"p{idx+1}"] = obj

    for f_idx, pts in enumerate(trajectory):
        fr = f_idx + 1
        for m_idx, pt in enumerate(pts):
            if pt is not None:
                lbl = labels[m_idx]
                obj = marker_objs[lbl]
                obj.location = (pt[0], pt[1], pt[2])
                obj.keyframe_insert(data_path="location", frame=fr)

    bones_list = ${JSON.stringify(bones)}
    if bones_list:
        arm_data = bpy.data.armatures.new("Armature_${trialName}")
        arm_obj = bpy.data.objects.new("Armature_${trialName}", arm_data)
        coll.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        created = []
        for (ja, jb) in bones_list:
            if ja in marker_objs and jb in marker_objs:
                oa = marker_objs[ja]
                ob = marker_objs[jb]
                b = arm_data.edit_bones.new(f"Bone_{ja}_{jb}")
                b.head = oa.location
                b.tail = ob.location
                created.append((b.name, ja, jb))
                
        bpy.ops.object.mode_set(mode='POSE')
        for (bname, ja, jb) in created:
            pb = arm_obj.pose.bones.get(bname)
            if pb:
                c1 = pb.constraints.new(type='COPY_LOCATION')
                c1.target = marker_objs[ja]
                c2 = pb.constraints.new(type='STRETCH_TO')
                c2.target = marker_objs[jb]

    print("[OpenBiomech] Import complete! Press Space in Blender to play.")

if __name__ == "__main__":
    build_openbiomech()
`;
  download(scriptContent, `${trialName}_blender.py`, "text/x-python");
  status("Script Blender (.py) exportado com sucesso!");
}

function exportBVHMotionFile() {
  if (!trial) {
    status("Nenhum trial carregado para exportar para BVH.", true);
    return;
  }
  status("Gerando arquivo BVH...");
  const trialName = $("title") ? $("title").textContent.replace(/[^a-zA-Z0-9_-]/g, "_") : "trial";
  const rateHz = trial.rate_hz > 0 ? trial.rate_hz : 100;
  const frameTime = (1 / rateHz).toFixed(8);

  const lines = ["HIERARCHY"];
  for (const label of trial.labels) {
    lines.push(`ROOT ${label}`);
    lines.push("{");
    lines.push("\tOFFSET 0.000000 0.000000 0.000000");
    lines.push("\tCHANNELS 3 Xposition Yposition Zposition");
    lines.push("\tEnd Site");
    lines.push("\t{");
    lines.push("\t\tOFFSET 0.000000 0.000000 0.000000");
    lines.push("\t}");
    lines.push("}");
  }
  lines.push("MOTION");
  lines.push(`Frames: ${trial.xyz.length}`);
  lines.push(`Frame Time: ${frameTime}`);

  const lastValid = trial.labels.map(() => [0, 0, 0]);
  for (const framePts of trial.xyz) {
    const vals = [];
    for (let i = 0; i < framePts.length; i++) {
      const pt = framePts[i];
      if (valid(pt)) {
        lastValid[i] = pt;
      }
      const p = lastValid[i];
      vals.push(p[0].toFixed(6), p[1].toFixed(6), p[2].toFixed(6));
    }
    lines.push(vals.join(" "));
  }

  download(lines.join("\n") + "\n", `${trialName}.bvh`, "text/plain");
  status("Arquivo BVH (.bvh) exportado com sucesso!");
}

if ($("action-export-blender")) $("action-export-blender").onclick = exportBlenderPythonScript;
if ($("action-export-bvh")) $("action-export-bvh").onclick = exportBVHMotionFile;

// Windows Menu Actions
if ($("action-win-3d")) $("action-win-3d").onclick = () => {
  const p = $("panel-3d"); p.hidden = !p.hidden; resize();
};
if ($("action-win-plot1")) $("action-win-plot1").onclick = () => {
  const p = $("panel-plot1"); p.hidden = !p.hidden; resize();
};
if ($("action-win-plot2")) $("action-win-plot2").onclick = () => {
  const p = $("panel-plot2"); p.hidden = !p.hidden; resize();
};
if ($("action-win-table")) $("action-win-table").onclick = () => {
  const p = $("panel-table"); p.hidden = !p.hidden; resize();
};

// Help & Shortcuts Modals
function openShortcutsModal() {
  const m = $("modal-shortcuts");
  if (m) m.classList.add("open");
}
function closeShortcutsModal() {
  const m = $("modal-shortcuts");
  if (m) m.classList.remove("open");
}

if ($("action-view-shortcuts")) $("action-view-shortcuts").onclick = openShortcutsModal;
if ($("action-help-shortcuts")) $("action-help-shortcuts").onclick = openShortcutsModal;
if ($("btn-close-shortcuts")) $("btn-close-shortcuts").onclick = closeShortcutsModal;

const shortcutsModalEl = $("modal-shortcuts");
if (shortcutsModalEl) {
  shortcutsModalEl.onclick = e => {
    if (e.target === shortcutsModalEl) closeShortcutsModal();
  };
}

if ($("action-help-about")) {
  $("action-help-about").onclick = () => {
    alert("mkvis3d · OpenBiomech\nModern biomechanical motion viewer & analysis suite\nCompatible with Vicon, Qualisys, C3D, CSV, and .3d formats.");
  };
}

// Keyboard shortcuts
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    document.querySelectorAll(".modal-backdrop.open").forEach(m => m.classList.remove("open"));
    return;
  }
  if (e.key === "?" || e.key === "F1") {
    if (!["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault();
      openShortcutsModal();
      return;
    }
  }
  if (["INPUT", "SELECT", "BUTTON", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); $("play").click(); }
  if (e.code === "ArrowLeft") step(-1);
  if (e.code === "ArrowRight") step(1);
  if (e.code === "Home") { e.preventDefault(); if ($("first")) $("first").click(); }
  if (e.code === "End") { e.preventDefault(); if ($("last")) $("last").click(); }
  if (e.key === "r" || e.key === "R") fit();
  if (e.key === "g" || e.key === "G") {
    if ($("grid")) { $("grid").checked = !$("grid").checked; draw(); saveSessionState(); }
  }
  if (e.key === "l" || e.key === "L") {
    if ($("labels")) { $("labels").checked = !$("labels").checked; draw(); saveSessionState(); }
  }
  if ((e.altKey && (e.key === "t" || e.key === "T")) || (e.shiftKey && (e.key === "T" || e.key === "t"))) {
    e.preventDefault();
    toggleTheme();
    return;
  }
  if (e.altKey && (e.key === "l" || e.key === "L")) {
    e.preventDefault();
    openLCSModal();
    return;
  }
  if (e.altKey && (e.key === "f" || e.key === "F")) {
    e.preventDefault();
    openFilterModal();
    return;
  }
  if (!e.altKey && !e.shiftKey && !e.ctrlKey && !e.metaKey && (e.key === "t" || e.key === "T")) {
    if ($("trail")) { $("trail").checked = !$("trail").checked; draw(); saveSessionState(); }
  }
  if (e.key === "b" || e.key === "B") {
    if ($("bones")) { $("bones").checked = !$("bones").checked; draw(); saveSessionState(); }
  }
  if (e.key === "d" || e.key === "D") {
    setDistanceVisible(!showDistance);
  }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "+" || e.key === "=")) {
    e.preventDefault();
    setMarkerSize(markerSize + 0.5);
    return;
  }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "-" || e.key === "_")) {
    e.preventDefault();
    setMarkerSize(markerSize - 0.5);
    return;
  }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey && (e.key === "c" || e.key === "C")) {
    e.preventDefault();
    cycleMarkerColor();
    return;
  }
});

// Download utility
function download(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("export").onclick = () => {
  const rows = ["frame,time_s,distance_m"];
  distances.forEach((d, i) => rows.push(`${i},${i / trial.rate_hz},${Number.isFinite(d) ? d : ""}`));
  download(rows.join("\n") + "\n", "distance.csv", "text/csv");
};

$("snapshot").onclick = () => {
  const root = document.documentElement.cloneNode(true);
  root.setAttribute("data-theme", currentTheme);
  root.setAttribute("data-marker-size", String(markerSize));
  root.setAttribute("data-marker-color", markerColor);
  root.querySelector("#trial-data").textContent = JSON.stringify({ server: false, trial }).replace(/</g, "\\u003c");
  download("<!doctype html>\n" + root.outerHTML, "movement.html", "text/html");
};

// Drag & Drop File Handling
window.addEventListener("dragover", e => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
window.addEventListener("drop", async e => {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

// File Upload Handler
async function uploadFile(file) {
  pause();
  status(`Uploading and parsing ${file.name}...`);
  if ($("file")) $("file").disabled = true;
  try {
    const params = new URLSearchParams({
      name: file.name,
      rate: $("rate") ? $("rate").value : "100",
      units: $("units") ? $("units").value : "m"
    });
    const response = await fetch(`/api/trial?${params}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/octet-stream"
      },
      body: file
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to open file.");
    load(data);
  } catch (error) {
    status(error.message, true);
  } finally {
    if ($("file")) {
      $("file").disabled = false;
      $("file").value = "";
    }
  }
}

if ($("file")) {
  $("file").onchange = () => {
    const file = $("file").files[0];
    if (file) uploadFile(file);
  };
}

if ($("btn-welcome-select")) {
  $("btn-welcome-select").onclick = () => {
    if ($("file")) $("file").click();
  };
}

function initMarkerControls() {
  const slider = $("marker-size-slider");
  const btnInc = $("btn-inc-marker-size");
  const btnDec = $("btn-dec-marker-size");
  const btnCycle = $("btn-cycle-marker-color");
  const colorPicker = $("marker-color-custom");
  const btnReset = $("btn-reset-marker-style");
  const swatchesContainer = $("marker-color-swatches");

  if (slider) {
    slider.oninput = e => setMarkerSize(Number(e.target.value));
  }
  if (btnInc) btnInc.onclick = () => setMarkerSize(markerSize + 0.5);
  if (btnDec) btnDec.onclick = () => setMarkerSize(markerSize - 0.5);
  if (btnCycle) btnCycle.onclick = cycleMarkerColor;
  if (btnReset) btnReset.onclick = resetMarkerStyle;
  if (colorPicker) {
    colorPicker.oninput = e => setMarkerColor(e.target.value, e.target.value);
  }

  // Populate color swatches
  if (swatchesContainer) {
    swatchesContainer.innerHTML = "";
    // Auto swatch (theme default)
    const autoBtn = document.createElement("button");
    autoBtn.type = "button";
    autoBtn.className = "color-swatch-btn" + (markerColor === "auto" ? " selected" : "");
    autoBtn.dataset.color = "auto";
    autoBtn.title = "Default (Theme Color)";
    autoBtn.style.background = currentTheme === "light" ? "#475569" : "#9bbed7";
    autoBtn.onclick = () => setMarkerColor("auto", "Default (Theme)");
    swatchesContainer.appendChild(autoBtn);

    // 11 predefined colors from viewc3d.py
    for (const item of MARKER_PALETTE) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "color-swatch-btn" + (markerColor === item.hex ? " selected" : "");
      btn.dataset.color = item.hex;
      btn.title = item.name;
      btn.style.background = item.hex;
      btn.onclick = () => setMarkerColor(item.hex, item.name);
      swatchesContainer.appendChild(btn);
    }
  }

  // Options menu items
  if ($("action-cycle-marker-color")) $("action-cycle-marker-color").onclick = cycleMarkerColor;
  if ($("action-inc-marker-size")) $("action-inc-marker-size").onclick = () => setMarkerSize(markerSize + 0.5);
  if ($("action-dec-marker-size")) $("action-dec-marker-size").onclick = () => setMarkerSize(markerSize - 0.5);
  if ($("action-reset-marker-style")) $("action-reset-marker-style").onclick = resetMarkerStyle;
}

function initVerticalSplitter() {
  const splitter = $("vertical-splitter");
  const container = $("windows-container");
  if (!splitter || !container) return;

  let isDragging = false;
  let startY = 0;
  let startHeight = 170;

  splitter.addEventListener("pointerdown", e => {
    isDragging = true;
    startY = e.clientY;
    splitter.classList.add("is-dragging");
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    const currentHeightStr = getComputedStyle(container).getPropertyValue("--plot-height").trim();
    startHeight = parseFloat(currentHeightStr) || 170;
    splitter.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  splitter.addEventListener("pointermove", e => {
    if (!isDragging) return;
    const dy = startY - e.clientY;
    const containerRect = container.getBoundingClientRect();
    const minHeight = 70;
    const maxHeight = Math.max(minHeight, containerRect.height - 100);
    const newHeight = Math.min(maxHeight, Math.max(minHeight, Math.round(startHeight + dy)));
    container.style.setProperty("--plot-height", `${newHeight}px`);
    resize();
  });

  const stopDrag = e => {
    if (isDragging) {
      isDragging = false;
      splitter.classList.remove("is-dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try { splitter.releasePointerCapture(e.pointerId); } catch (_) {}
      saveSessionState();
    }
  };

  splitter.addEventListener("pointerup", stopDrag);
  splitter.addEventListener("pointercancel", stopDrag);

  splitter.addEventListener("dblclick", () => {
    container.style.setProperty("--plot-height", "170px");
    resize();
    saveSessionState();
  });
}

// ============================================================================
// Visual3D Laboratory Coordinate System (LCS) & Signal Conditioning Module
// ============================================================================

const DIRECTION_VECTORS = {
  "+X": [1, 0, 0],
  "-X": [-1, 0, 0],
  "+Y": [0, 1, 0],
  "-Y": [0, -1, 0],
  "+Z": [0, 0, 1],
  "-Z": [0, 0, -1]
};

const LCS_PRESETS = {
  isb_default: { ap: "+Y", axial: "+Z", label: "ISB (+Z Up, +Y AP)" },
  y_up_bvh: { ap: "+Z", axial: "+Y", label: "BVH / Unity (+Y Up, +Z AP)" },
  y_up_threejs: { ap: "-Z", axial: "+Y", label: "Three.js (+Y Up, -Z AP)" },
  x_up: { ap: "+Y", axial: "+X", label: "X-Up (+X Up, +Y AP)" },
  walkway_x: { ap: "+X", axial: "+Z", label: "Walkway X (+Z Up, +X AP)" },
  reverse_walkway: { ap: "-Y", axial: "+Z", label: "Reverse Walk (-Y AP)" }
};

function dot3(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross3(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function computeLCSMatrix(apKey, axialKey) {
  const v_ap = DIRECTION_VECTORS[apKey];
  const v_axial = DIRECTION_VECTORS[axialKey];
  if (!v_ap || !v_axial) {
    return { valid: false, error: "Invalid vector direction specified." };
  }
  const dot = dot3(v_ap, v_axial);
  if (Math.abs(dot) > 1e-4) {
    return { valid: false, error: `AP direction (${apKey}) and Axial direction (${axialKey}) must be orthogonal.` };
  }
  // Visual3D convention: ML = AP x AXIAL
  const v_ml = cross3(v_ap, v_axial);
  let mlName = "?";
  for (const [name, vec] of Object.entries(DIRECTION_VECTORS)) {
    if (Math.abs(vec[0] - v_ml[0]) < 1e-4 &&
        Math.abs(vec[1] - v_ml[1]) < 1e-4 &&
        Math.abs(vec[2] - v_ml[2]) < 1e-4) {
      mlName = name;
      break;
    }
  }

  // Row 0 = v_ml, Row 1 = v_ap, Row 2 = v_axial
  const R = [v_ml, v_ap, v_axial];
  const det = R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1]) -
              R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0]) +
              R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]);

  return { valid: true, R, mlName, det };
}

function applyLCSToXYZ(xyz, R) {
  const nFrames = xyz.length;
  const out = new Array(nFrames);
  const r00 = R[0][0], r01 = R[0][1], r02 = R[0][2];
  const r10 = R[1][0], r11 = R[1][1], r12 = R[1][2];
  const r20 = R[2][0], r21 = R[2][1], r22 = R[2][2];

  for (let f = 0; f < nFrames; f++) {
    const framePts = xyz[f];
    const nMarkers = framePts.length;
    const newPts = new Array(nMarkers);
    for (let m = 0; m < nMarkers; m++) {
      const p = framePts[m];
      if (p && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Number.isFinite(p[2])) {
        const x = p[0], y = p[1], z = p[2];
        newPts[m] = [
          r00 * x + r01 * y + r02 * z,
          r10 * x + r11 * y + r12 * z,
          r20 * x + r21 * y + r22 * z
        ];
      } else {
        newPts[m] = null;
      }
    }
    out[f] = newPts;
  }
  return out;
}

// ---------------------------------------------------------------------------
// 1D Signal Processing Algorithms (Pure JavaScript, Zero External CDN)
// ---------------------------------------------------------------------------

function gapFill1D(series, method = "linear", maxGap = 0) {
  const n = series.length;
  const out = series.slice();
  let i = 0;
  while (i < n) {
    if (out[i] !== null && Number.isFinite(out[i])) {
      i++;
      continue;
    }
    const gapStart = i;
    while (i < n && (out[i] === null || !Number.isFinite(out[i]))) {
      i++;
    }
    const gapEnd = i - 1;
    const gapLen = gapEnd - gapStart + 1;

    const i0 = gapStart - 1;
    const i1 = gapEnd + 1;
    const hasLeft = i0 >= 0 && out[i0] !== null && Number.isFinite(out[i0]);
    const hasRight = i1 < n && out[i1] !== null && Number.isFinite(out[i1]);

    if (maxGap > 0 && gapLen > maxGap) {
      continue;
    }
    if (!hasLeft && !hasRight) {
      continue;
    }
    if (!hasLeft) {
      for (let k = gapStart; k <= gapEnd; k++) out[k] = out[i1];
      continue;
    }
    if (!hasRight) {
      for (let k = gapStart; k <= gapEnd; k++) out[k] = out[i0];
      continue;
    }

    const y0 = out[i0], y1 = out[i1];
    const dx = i1 - i0;

    if (method === "nearest") {
      const mid = (i0 + i1) / 2;
      for (let k = gapStart; k <= gapEnd; k++) {
        out[k] = k < mid ? y0 : y1;
      }
    } else if (method === "cubic" && i0 > 0 && i1 < n - 1) {
      const prevIdx = i0 > 0 && Number.isFinite(out[i0 - 1]) ? i0 - 1 : i0;
      const nextIdx = i1 < n - 1 && Number.isFinite(out[i1 + 1]) ? i1 + 1 : i1;
      const m0 = (out[i1] - out[prevIdx]) / Math.max(1, i1 - prevIdx);
      const m1 = (out[nextIdx] - out[i0]) / Math.max(1, nextIdx - i0);

      for (let k = gapStart; k <= gapEnd; k++) {
        const t = (k - i0) / dx;
        const t2 = t * t;
        const t3 = t2 * t;
        const h00 = 2 * t3 - 3 * t2 + 1;
        const h10 = t3 - 2 * t2 + t;
        const h01 = -2 * t3 + 3 * t2;
        const h11 = t3 - t2;
        out[k] = h00 * y0 + h10 * dx * m0 + h01 * y1 + h11 * dx * m1;
      }
    } else {
      // Linear default
      for (let k = gapStart; k <= gapEnd; k++) {
        const t = (k - i0) / dx;
        out[k] = y0 + t * (y1 - y0);
      }
    }
  }
  return out;
}

function hampelFilter1D(series, windowSize = 7, nSigmas = 3.0) {
  const n = series.length;
  const out = series.slice();
  const half = Math.floor(windowSize / 2);

  for (let i = 0; i < n; i++) {
    if (out[i] === null || !Number.isFinite(out[i])) continue;
    const windowVals = [];
    const wStart = Math.max(0, i - half);
    const wEnd = Math.min(n - 1, i + half);
    for (let k = wStart; k <= wEnd; k++) {
      if (series[k] !== null && Number.isFinite(series[k])) {
        windowVals.push(series[k]);
      }
    }
    if (windowVals.length < 3) continue;
    windowVals.sort((a, b) => a - b);
    const midIdx = Math.floor(windowVals.length / 2);
    const med = windowVals.length % 2 === 1
      ? windowVals[midIdx]
      : (windowVals[midIdx - 1] + windowVals[midIdx]) / 2;

    const diffs = windowVals.map(v => Math.abs(v - med)).sort((a, b) => a - b);
    const mad = diffs.length % 2 === 1
      ? diffs[midIdx]
      : (diffs[midIdx - 1] + diffs[midIdx]) / 2;

    const threshold = 1.4826 * nSigmas * Math.max(mad, 1e-6);
    if (Math.abs(series[i] - med) > threshold) {
      out[i] = med;
    }
  }
  return out;
}

function medianFilter1D(series, windowSize = 5) {
  const n = series.length;
  const filled = gapFill1D(series, "nearest", 0);
  const out = new Array(n);
  const half = Math.floor(windowSize / 2);

  for (let i = 0; i < n; i++) {
    const vals = [];
    const wStart = Math.max(0, i - half);
    const wEnd = Math.min(n - 1, i + half);
    for (let k = wStart; k <= wEnd; k++) {
      vals.push(filled[k]);
    }
    vals.sort((a, b) => a - b);
    const mid = Math.floor(vals.length / 2);
    out[i] = vals.length % 2 === 1 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
  }
  return out;
}

function movingAverage1D(series, windowSize = 5) {
  const n = series.length;
  const filled = gapFill1D(series, "nearest", 0);
  const out = new Array(n);
  const half = Math.floor(windowSize / 2);

  for (let i = 0; i < n; i++) {
    let sum = 0, count = 0;
    const wStart = Math.max(0, i - half);
    const wEnd = Math.min(n - 1, i + half);
    for (let k = wStart; k <= wEnd; k++) {
      sum += filled[k];
      count++;
    }
    out[i] = sum / count;
  }
  return out;
}

function butterworthLowpassZeroPhase(series, fs, cutoff = 6.0) {
  const n = series.length;
  if (n < 6) return series.slice();

  // Gap-fill NaNs linearly before filtering to avoid boundary explosion
  const filled = gapFill1D(series, "linear", 0);

  const nyq = 0.5 * fs;
  const fcClamped = Math.max(0.1, Math.min(cutoff, nyq * 0.95));
  const wa = Math.tan(Math.PI * fcClamped / fs);

  const a0 = 1.0 + Math.SQRT2 * wa + wa * wa;
  const b0 = (wa * wa) / a0;
  const b1 = 2.0 * b0;
  const b2 = b0;
  const a1 = 2.0 * (wa * wa - 1.0) / a0;
  const a2 = (1.0 - Math.SQRT2 * wa + wa * wa) / a0;

  // Odd reflection padding
  const pad = Math.min(30, n - 1);
  const totalLen = n + 2 * pad;
  const padded = new Float64Array(totalLen);

  for (let i = 0; i < pad; i++) {
    padded[i] = 2 * filled[0] - filled[pad - i];
  }
  for (let i = 0; i < n; i++) {
    padded[pad + i] = filled[i];
  }
  for (let i = 0; i < pad; i++) {
    padded[pad + n + i] = 2 * filled[n - 1] - filled[n - 2 - i];
  }

  // Forward pass
  const forward = new Float64Array(totalLen);
  for (let i = 0; i < totalLen; i++) {
    const x0 = padded[i];
    const x1 = i > 0 ? padded[i - 1] : padded[0];
    const x2 = i > 1 ? padded[i - 2] : padded[0];
    const y1 = i > 0 ? forward[i - 1] : padded[0];
    const y2 = i > 1 ? forward[i - 2] : padded[0];
    forward[i] = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  }

  // Backward pass
  const backward = new Float64Array(totalLen);
  for (let i = totalLen - 1; i >= 0; i--) {
    const x0 = forward[i];
    const x1 = i < totalLen - 1 ? forward[i + 1] : forward[totalLen - 1];
    const x2 = i < totalLen - 2 ? forward[i + 2] : forward[totalLen - 1];
    const y1 = i < totalLen - 1 ? backward[i + 1] : forward[totalLen - 1];
    const y2 = i < totalLen - 2 ? backward[i + 2] : forward[totalLen - 1];
    backward[i] = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  }

  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    out[i] = backward[pad + i];
  }
  return out;
}

function processSeries1D(series, fs, options) {
  let cur = series.slice();
  if (options.hampel) {
    cur = hampelFilter1D(cur, options.hampelWindow || 7, options.hampelSigmas || 3.0);
  }
  if (options.interp && options.interp !== "none") {
    cur = gapFill1D(cur, options.interp, options.maxGap || 0);
  }
  if (options.smooth === "butterworth") {
    cur = butterworthLowpassZeroPhase(cur, fs, options.cutoff || 6.0);
  } else if (options.smooth === "moving_average") {
    cur = movingAverage1D(cur, options.windowSize || 5);
  } else if (options.smooth === "median") {
    cur = medianFilter1D(cur, options.windowSize || 5);
  }
  return cur;
}

function applyFilterToXYZ(xyz, fs, config) {
  const nFrames = xyz.length;
  if (nFrames === 0) return xyz;
  const nMarkers = xyz[0].length;
  const out = new Array(nFrames);
  for (let f = 0; f < nFrames; f++) {
    out[f] = new Array(nMarkers);
  }

  const markersToProcess = [];
  if (config.scope === "active" && activeMarkerIndex >= 0 && activeMarkerIndex < nMarkers) {
    markersToProcess.push(activeMarkerIndex);
  } else {
    for (let m = 0; m < nMarkers; m++) markersToProcess.push(m);
  }

  for (let m = 0; m < nMarkers; m++) {
    if (!markersToProcess.includes(m)) {
      for (let f = 0; f < nFrames; f++) {
        const p = xyz[f][m];
        out[f][m] = p ? [p[0], p[1], p[2]] : null;
      }
    }
  }

  for (const m of markersToProcess) {
    const xRaw = new Array(nFrames);
    const yRaw = new Array(nFrames);
    const zRaw = new Array(nFrames);
    for (let f = 0; f < nFrames; f++) {
      const p = xyz[f][m];
      if (p && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Number.isFinite(p[2])) {
        xRaw[f] = p[0];
        yRaw[f] = p[1];
        zRaw[f] = p[2];
      } else {
        xRaw[f] = NaN;
        yRaw[f] = NaN;
        zRaw[f] = NaN;
      }
    }

    const xProc = processSeries1D(xRaw, fs, config);
    const yProc = processSeries1D(yRaw, fs, config);
    const zProc = processSeries1D(zRaw, fs, config);

    for (let f = 0; f < nFrames; f++) {
      const x = xProc[f], y = yProc[f], z = zProc[f];
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
        out[f][m] = [x, y, z];
      } else {
        out[f][m] = null;
      }
    }
  }

  return out;
}

function recomputeTrialXYZ() {
  if (!trial || !rawLoadedXYZ) return;

  let workingXYZ = rawLoadedXYZ;

  // Apply LCS
  if (currentLCS.ap !== "+Y" || currentLCS.axial !== "+Z") {
    const lcsRes = computeLCSMatrix(currentLCS.ap, currentLCS.axial);
    if (lcsRes.valid) {
      workingXYZ = applyLCSToXYZ(workingXYZ, lcsRes.R);
      if (rawForcePlates) {
        const R = lcsRes.R;
        trial.force_plates = rawForcePlates.map(fp => ({
          ...fp,
          corners: fp.corners.map(c => [
            R[0][0] * c[0] + R[0][1] * c[1] + R[0][2] * c[2],
            R[1][0] * c[0] + R[1][1] * c[1] + R[1][2] * c[2],
            R[2][0] * c[0] + R[2][1] * c[1] + R[2][2] * c[2],
          ]),
          cop: fp.cop.map(p => p ? [
            R[0][0] * p[0] + R[0][1] * p[1] + R[0][2] * p[2],
            R[1][0] * p[0] + R[1][1] * p[1] + R[1][2] * p[2],
            R[2][0] * p[0] + R[2][1] * p[1] + R[2][2] * p[2],
          ] : null),
          force: fp.force.map(f => f ? [
            R[0][0] * f[0] + R[0][1] * f[1] + R[0][2] * f[2],
            R[1][0] * f[0] + R[1][1] * f[1] + R[1][2] * f[2],
            R[2][0] * f[0] + R[2][1] * f[1] + R[2][2] * f[2],
          ] : [0, 0, 0]),
        }));
      }
    }
  } else if (rawForcePlates) {
    trial.force_plates = JSON.parse(JSON.stringify(rawForcePlates));
  }

  // Apply Filter
  if (activeFilterConfig) {
    workingXYZ = applyFilterToXYZ(workingXYZ, trial.rate_hz, activeFilterConfig);
  }

  trial.xyz = workingXYZ;
  fit();
  measure();
  updateTable();
  draw();
  saveSessionState();
}

function updateLCSUI() {
  const badge = $("lcs-active-badge");
  if (!badge) return;
  if (currentLCS.ap === "+Y" && currentLCS.axial === "+Z") {
    badge.textContent = "LCS: ISB (+Y AP, +Z Axial)";
    badge.style.color = "var(--text-muted)";
  } else {
    let label = `LCS: ${currentLCS.ap} AP, ${currentLCS.axial} Axial`;
    for (const key in LCS_PRESETS) {
      if (LCS_PRESETS[key].ap === currentLCS.ap && LCS_PRESETS[key].axial === currentLCS.axial) {
        label = `LCS: ${LCS_PRESETS[key].label}`;
        break;
      }
    }
    badge.textContent = label;
    badge.style.color = "var(--accent)";
  }
}

function updateFilterUI() {
  const badge = $("filter-status-badge");
  const btnRevert = $("btn-revert-filter");
  const btnDialogRevert = $("btn-dialog-revert-filter");

  if (!badge) return;
  if (activeFilterConfig) {
    let desc = "";
    if (activeFilterConfig.smooth === "butterworth") {
      desc = `BW ${activeFilterConfig.cutoff}Hz`;
    } else if (activeFilterConfig.smooth === "moving_average") {
      desc = `MA (${activeFilterConfig.windowSize}f)`;
    } else if (activeFilterConfig.smooth === "median") {
      desc = `Median (${activeFilterConfig.windowSize}f)`;
    } else {
      desc = "Gap Fill";
    }
    if (activeFilterConfig.interp && activeFilterConfig.interp !== "none") {
      desc += ` + ${activeFilterConfig.interp}`;
    }
    if (activeFilterConfig.scope === "active") {
      desc += " [Active]";
    }
    badge.textContent = desc;
    badge.style.color = "var(--accent)";
    if (btnRevert) btnRevert.disabled = false;
    if (btnDialogRevert) btnDialogRevert.disabled = false;
  } else {
    badge.textContent = "Raw";
    badge.style.color = "var(--text-muted)";
    if (btnRevert) btnRevert.disabled = true;
    if (btnDialogRevert) btnDialogRevert.disabled = true;
  }
}

function openLCSModal() {
  const modal = $("modal-lcs");
  if (!modal) return;
  if ($("lcs-axial-select")) $("lcs-axial-select").value = currentLCS.axial;
  if ($("lcs-ap-select")) $("lcs-ap-select").value = currentLCS.ap;
  updateLCSFeedback();
  modal.classList.add("open");
}

function closeLCSModal() {
  const modal = $("modal-lcs");
  if (modal) modal.classList.remove("open");
}

function updateLCSFeedback() {
  const axial = $("lcs-axial-select") ? $("lcs-axial-select").value : "+Z";
  const ap = $("lcs-ap-select") ? $("lcs-ap-select").value : "+Y";
  const res = computeLCSMatrix(ap, axial);

  const mlEl = $("lcs-ml-result");
  const detEl = $("lcs-det-result");
  const errEl = $("lcs-error-msg");
  const btnApply = $("btn-apply-lcs");

  if (res.valid) {
    if (mlEl) mlEl.textContent = res.mlName;
    if (detEl) {
      detEl.textContent = `Right-Handed System (det = +${res.det.toFixed(1)})`;
      detEl.style.color = "#22c55e";
    }
    if (errEl) errEl.style.display = "none";
    if (btnApply) btnApply.disabled = false;
  } else {
    if (mlEl) mlEl.textContent = "Invalid (Collinear)";
    if (detEl) {
      detEl.textContent = "Cannot construct basis";
      detEl.style.color = "#ef4444";
    }
    if (errEl) {
      errEl.textContent = res.error;
      errEl.style.display = "block";
    }
    if (btnApply) btnApply.disabled = true;
  }

  document.querySelectorAll(".btn-lcs-preset").forEach(btn => {
    const p = LCS_PRESETS[btn.dataset.preset];
    btn.classList.toggle("active", p && p.ap === ap && p.axial === axial);
  });
}

function applyLCS(apKey, axialKey) {
  const res = computeLCSMatrix(apKey, axialKey);
  if (!res.valid) {
    status(`LCS Error: ${res.error}`);
    return;
  }
  currentLCS = { ap: apKey, axial: axialKey };
  recomputeTrialXYZ();
  updateLCSUI();
  closeLCSModal();
  status(`Laboratory Coordinate System (LCS) applied: AP=${apKey}, Axial=${axialKey}, ML=${res.mlName}.`);
}

function resetLCS() {
  currentLCS = { ap: "+Y", axial: "+Z" };
  if ($("lcs-axial-select")) $("lcs-axial-select").value = "+Z";
  if ($("lcs-ap-select")) $("lcs-ap-select").value = "+Y";
  updateLCSFeedback();
  recomputeTrialXYZ();
  updateLCSUI();
  closeLCSModal();
  status("Laboratory Coordinate System reset to standard ISB (+Y AP, +Z Axial).");
}

function getModalFilterConfig() {
  const hampel = $("flt-hampel-enable") ? $("flt-hampel-enable").checked : false;
  const hampelWindow = parseInt($("flt-hampel-window")?.value || "7", 10);
  const hampelSigmas = parseFloat($("flt-hampel-sigmas")?.value || "3.0");
  const interp = $("flt-interp-method")?.value || "linear";
  const maxGap = parseInt($("flt-max-gap")?.value || "10", 10);
  const smooth = $("flt-smooth-method")?.value || "butterworth";
  const cutoff = parseFloat($("flt-cutoff-slider")?.value || "6.0");
  const windowSize = parseInt($("flt-window-size")?.value || "5", 10);
  const scopeEl = document.querySelector('input[name="flt-scope"]:checked');
  const scope = scopeEl ? scopeEl.value : "all";

  return {
    hampel,
    hampelWindow,
    hampelSigmas,
    interp,
    maxGap,
    smooth,
    cutoff,
    windowSize,
    scope
  };
}

function updateFilterPreview() {
  if (!trial) return;
  const previewCheck = $("flt-preview-check");
  if (!previewCheck || !previewCheck.checked) {
    filterPreviewActive = false;
    filterPreviewSeries = null;
    drawPlots();
    return;
  }

  const config = getModalFilterConfig();
  const mode = $("plot1-mode") ? $("plot1-mode").value : "active-z";

  let rawValues = null;
  if (mode === "active-z") {
    rawValues = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
  } else if (mode === "distance") {
    rawValues = distances.slice();
  } else if (mode === "active-xyz") {
    rawValues = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
  } else if (mode === "active-speed") {
    const speedVals = [0];
    for (let i = 1; i < trial.xyz.length; i++) {
      const p = trial.xyz[i - 1][activeMarkerIndex], q = trial.xyz[i][activeMarkerIndex];
      if (valid(p) && valid(q)) {
        speedVals.push(Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]) * trial.rate_hz);
      } else {
        speedVals.push(NaN);
      }
    }
    rawValues = speedVals;
  }

  if (rawValues) {
    const processed = processSeries1D(rawValues, trial.rate_hz, config);
    filterPreviewSeries = {
      name: "Candidate Filter",
      color: currentTheme === "light" ? "#dc2626" : "#38bdf8",
      values: processed
    };
    filterPreviewActive = true;
  } else {
    filterPreviewActive = false;
    filterPreviewSeries = null;
  }
  drawPlots();
}

function openFilterModal() {
  const modal = $("modal-filter");
  if (!modal) return;
  if (trial && $("flt-fs-readout")) $("flt-fs-readout").textContent = trial.rate_hz.toFixed(1);
  if (trial && $("flt-nyq-readout")) $("flt-nyq-readout").textContent = (trial.rate_hz / 2).toFixed(1);
  if (trial && trial.labels && trial.labels[activeMarkerIndex] && $("flt-active-marker-name")) {
    $("flt-active-marker-name").textContent = trial.labels[activeMarkerIndex];
  }
  updateFilterPreview();
  modal.classList.add("open");
}

function closeFilterModal() {
  const modal = $("modal-filter");
  if (modal) modal.classList.remove("open");
  filterPreviewActive = false;
  filterPreviewSeries = null;
  drawPlots();
}

function applyFilter() {
  const config = getModalFilterConfig();
  activeFilterConfig = config;
  closeFilterModal();
  recomputeTrialXYZ();
  updateFilterUI();
  status(`Applied signal conditioning: ${activeFilterConfig.smooth} filter, gap-fill: ${activeFilterConfig.interp}.`);
}

function revertFilter() {
  activeFilterConfig = null;
  recomputeTrialXYZ();
  updateFilterUI();
  closeFilterModal();
  status("Reverted trial trajectories to raw unfiltered data.");
}

function initLCSAndFilterControls() {
  // Sidebar buttons
  if ($("btn-open-lcs")) $("btn-open-lcs").onclick = openLCSModal;
  if ($("btn-open-filter")) $("btn-open-filter").onclick = openFilterModal;
  if ($("btn-quick-filter")) $("btn-quick-filter").onclick = () => {
    activeFilterConfig = {
      hampel: false,
      interp: "linear",
      maxGap: 10,
      smooth: "butterworth",
      cutoff: 6.0,
      windowSize: 5,
      scope: "all"
    };
    recomputeTrialXYZ();
    updateFilterUI();
    status("Applied Quick Smooth: Zero-phase 6 Hz Butterworth filter & linear gap-fill.");
  };
  if ($("btn-revert-filter")) $("btn-revert-filter").onclick = revertFilter;

  // View & Options menu items
  if ($("action-view-lcs")) $("action-view-lcs").onclick = openLCSModal;
  if ($("action-view-filter")) $("action-view-filter").onclick = openFilterModal;
  if ($("action-opt-lcs")) $("action-opt-lcs").onclick = openLCSModal;
  if ($("action-opt-filter")) $("action-opt-filter").onclick = openFilterModal;

  // LCS Dialog
  if ($("btn-close-lcs")) $("btn-close-lcs").onclick = closeLCSModal;
  if ($("btn-cancel-lcs")) $("btn-cancel-lcs").onclick = closeLCSModal;
  if ($("btn-reset-lcs")) $("btn-reset-lcs").onclick = resetLCS;
  if ($("btn-apply-lcs")) $("btn-apply-lcs").onclick = () => {
    const axial = $("lcs-axial-select") ? $("lcs-axial-select").value : "+Z";
    const ap = $("lcs-ap-select") ? $("lcs-ap-select").value : "+Y";
    applyLCS(ap, axial);
  };
  if ($("lcs-axial-select")) $("lcs-axial-select").onchange = updateLCSFeedback;
  if ($("lcs-ap-select")) $("lcs-ap-select").onchange = updateLCSFeedback;

  document.querySelectorAll(".btn-lcs-preset").forEach(btn => {
    btn.onclick = () => {
      const p = LCS_PRESETS[btn.dataset.preset];
      if (p) {
        if ($("lcs-axial-select")) $("lcs-axial-select").value = p.axial;
        if ($("lcs-ap-select")) $("lcs-ap-select").value = p.ap;
        updateLCSFeedback();
      }
    };
  });

  // Filter Dialog
  if ($("btn-close-filter")) $("btn-close-filter").onclick = closeFilterModal;
  if ($("btn-cancel-filter")) $("btn-cancel-filter").onclick = closeFilterModal;
  if ($("btn-apply-filter")) $("btn-apply-filter").onclick = applyFilter;
  if ($("btn-dialog-revert-filter")) $("btn-dialog-revert-filter").onclick = revertFilter;

  if ($("flt-cutoff-slider")) {
    $("flt-cutoff-slider").oninput = () => {
      const v = parseFloat($("flt-cutoff-slider").value);
      if ($("flt-cutoff-val")) $("flt-cutoff-val").textContent = `${v.toFixed(1)} Hz`;
      updateFilterPreview();
    };
  }

  if ($("flt-smooth-method")) {
    $("flt-smooth-method").onchange = () => {
      const val = $("flt-smooth-method").value;
      if (val === "butterworth") {
        if ($("flt-cutoff-group")) $("flt-cutoff-group").style.display = "block";
        if ($("flt-window-group")) $("flt-window-group").style.display = "none";
      } else if (val === "moving_average" || val === "median") {
        if ($("flt-cutoff-group")) $("flt-cutoff-group").style.display = "none";
        if ($("flt-window-group")) $("flt-window-group").style.display = "block";
      } else {
        if ($("flt-cutoff-group")) $("flt-cutoff-group").style.display = "none";
        if ($("flt-window-group")) $("flt-window-group").style.display = "none";
      }
      updateFilterPreview();
    };
  }

  for (const id of ["flt-hampel-enable", "flt-hampel-window", "flt-hampel-sigmas", "flt-interp-method", "flt-max-gap", "flt-window-size", "flt-preview-check"]) {
    if ($(id)) $(id).onchange = updateFilterPreview;
  }
  document.querySelectorAll('input[name="flt-scope"]').forEach(r => {
    r.onchange = updateFilterPreview;
  });
}

$("open-panel").hidden = !boot.server;

// Initial loading: check inlined trial, then check server active trial
if (boot.trial) {
  load(boot.trial);
} else if (boot.server) {
  fetch("/api/current_trial")
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data) load(data);
    })
    .catch(() => {});
}

initMarkerControls();
initLCSAndFilterControls();
initVerticalSplitter();
resize();
setTheme(currentTheme);
setMarkerSize(markerSize);
setMarkerColor(markerColor);
