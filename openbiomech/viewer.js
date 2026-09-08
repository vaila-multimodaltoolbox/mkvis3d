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

function projectOriented(p) {
  const diff = [p[0] - center[0], p[1] - center[1], p[2] - center[2]];
  const x = Math.cos(yaw) * diff[0] - Math.sin(yaw) * diff[1];
  const depth = Math.sin(yaw) * diff[0] + Math.cos(yaw) * diff[1];
  const z = Math.cos(pitch) * diff[2] - Math.sin(pitch) * depth;
  const s = Math.min(canvas.clientWidth, canvas.clientHeight) * 0.75 / span * zoom;
  return [canvas.clientWidth / 2 + x * s + pan[0], canvas.clientHeight / 2 - z * s + pan[1], depth];
}

function project(raw) {
  return projectOriented(orient(raw));
}

function line(a, b, color, width = 1) {
  const p = project(a), q = project(b);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(p[0], p[1]);
  ctx.lineTo(q[0], q[1]);
  ctx.stroke();
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
function drawGroundGrid() {
  if (!$("grid") || !$("grid").checked) return;
  const floorH = getFloorHeight();
  const gridSize = Math.max(span * 1.5, 2.0);
  const step = gridSize > 5 ? 1.0 : gridSize > 2 ? 0.5 : 0.2;
  const count = Math.min(20, Math.ceil(gridSize / step));
  const extent = count * step;

  ctx.lineWidth = 1;
  for (let i = -count; i <= count; i++) {
    const x = i * step;
    const isCenter = i === 0;
    ctx.strokeStyle = isCenter ? "rgba(239, 134, 134, 0.6)" : "rgba(75, 105, 135, 0.25)";
    ctx.lineWidth = isCenter ? 1.5 : 1;
    const p1 = projectOriented([center[0] + x, center[1] - extent, floorH]);
    const p2 = projectOriented([center[0] + x, center[1] + extent, floorH]);
    ctx.beginPath();
    ctx.moveTo(p1[0], p1[1]);
    ctx.lineTo(p2[0], p2[1]);
    ctx.stroke();
  }
  for (let i = -count; i <= count; i++) {
    const y = i * step;
    const isCenter = i === 0;
    ctx.strokeStyle = isCenter ? "rgba(130, 217, 157, 0.6)" : "rgba(75, 105, 135, 0.25)";
    ctx.lineWidth = isCenter ? 1.5 : 1;
    const p1 = projectOriented([center[0] - extent, center[1] + y, floorH]);
    const p2 = projectOriented([center[0] + extent, center[1] + y, floorH]);
    ctx.beginPath();
    ctx.moveTo(p1[0], p1[1]);
    ctx.lineTo(p2[0], p2[1]);
    ctx.stroke();
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

function drawSkeleton(pts) {
  if (!$("bones") || !$("bones").checked || !skeletonPairs.length || !pts) return;
  for (const [i, j] of skeletonPairs) {
    if (valid(pts[i]) && valid(pts[j])) {
      line(pts[i], pts[j], "rgba(110, 160, 205, 0.75)", 2);
    }
  }
}

// 3D Scene Rendering
function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);
  if (!trial) return;

  drawGroundGrid();

  const pts = trial.xyz[frame] || [];
  const activeIdx = activeMarkerIndex;
  const a = Number($("marker-a") ? $("marker-a").value : 0);
  const b = Number($("marker-b") ? $("marker-b").value : 1);

  // Coordinate axes at origin
  const origin = [0, 0, 0];
  const axesColors = ["#ef8686", "#82d99d", "#7faeeb"];
  const axesLabels = ["X", "Y", "Z"];
  for (let i = 0; i < 3; i++) {
    const end = [0, 0, 0]; end[i] = span * 0.22;
    line(origin, end, axesColors[i], 2);
    const p = project(end);
    ctx.fillStyle = axesColors[i];
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillText(axesLabels[i], p[0] + 5, p[1]);
  }

  // Draw Skeleton Bones
  drawSkeleton(pts);

  // Trajectory Trail of active marker
  if ($("trail") && $("trail").checked && activeIdx >= 0 && activeIdx < trial.labels.length) {
    for (let f = Math.max(1, frame - 120); f <= frame; f++) {
      const p = trial.xyz[f - 1][activeIdx], q = trial.xyz[f][activeIdx];
      if (valid(p) && valid(q)) line(p, q, "#35827c", 1.5);
    }
  }

  // Distance line between Marker A and B (optional toggle)
  if (showDistance && valid(pts[a]) && valid(pts[b])) {
    line(pts[a], pts[b], "#f2c875", 2);
  }

  // Render Marker Points
  const visible = pts.map((p, i) => ({ p, i })).filter(v => valid(v.p)).map(v => ({ ...v, q: project(v.p) })).sort((a, b) => b.q[2] - a.q[2]);

  for (const { i, q } of visible) {
    const isAct = i === activeIdx;
    const isA = showDistance && i === a, isB = showDistance && i === b;
    ctx.beginPath();
    const radius = isAct ? 6 : (isA || isB ? 5 : 3.5);
    ctx.arc(q[0], q[1], radius, 0, Math.PI * 2);
    ctx.fillStyle = isAct ? "#59dec3" : (isA ? "#59dec3" : (isB ? "#f2c875" : "#9bbed7"));
    ctx.fill();

    if (isAct) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    if ($("labels") && $("labels").checked) {
      ctx.fillStyle = isAct ? "#ffffff" : "#adbdcd";
      ctx.font = (isAct ? "bold 11px" : "10px") + " system-ui, sans-serif";
      ctx.fillText(trial.labels[i], q[0] + 7, q[1] - 5);
    }
  }

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

function getSeriesForMode(mode) {
  const series = [];
  const totalFrames = trial.xyz.length;
  if (mode === "distance") {
    series.push({ name: "Distance", color: "#f2c875", values: distances });
  } else if (mode === "active-z") {
    const vals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
    series.push({ name: "Z (Height)", color: "#59dec3", values: vals });
  } else if (mode === "active-xyz") {
    const xVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][0] : NaN);
    const yVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][1] : NaN);
    const zVals = trial.xyz.map(p => valid(p[activeMarkerIndex]) ? p[activeMarkerIndex][2] : NaN);
    series.push({ name: "X", color: "#ef8686", values: xVals });
    series.push({ name: "Y", color: "#82d99d", values: yVals });
    series.push({ name: "Z", color: "#59dec3", values: zVals });
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
    series.push({ name: "Speed (m/s)", color: "#a38bf5", values: speedVals });
  }
  return series;
}

function drawSinglePlot(canvasG, gx, mode, readoutEl, plotId) {
  const w = canvasG.clientWidth, h = canvasG.clientHeight;
  gx.clearRect(0, 0, w, h);
  if (!trial) return;

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
  if (!Number.isFinite(lo)) return;
  const extent = Math.max(hi - lo, 0.001);
  const totalFrames = trial.xyz.length;

  if (readoutEl) {
    const curVals = series.map(s => {
      const v = s.values[frame];
      return `${s.name}: ${Number.isFinite(v) ? v.toFixed(3) : "—"}`;
    }).join("  |  ");
    readoutEl.textContent = curVals;
  }

  gx.strokeStyle = "rgba(255, 255, 255, 0.08)";
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

  gx.fillStyle = "#8298ad";
  gx.font = "10px system-ui, sans-serif";
  gx.fillText(`${hi.toFixed(3)}`, 2, 14);
  gx.fillText(`${lo.toFixed(3)}`, 2, h - 10);

  const curX = 50 + frame * (w - 65) / Math.max(1, totalFrames - 1);
  gx.strokeStyle = "#f2c875";
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
  for (let i = 0; i < trial.labels.length; i++) {
    const row = tbody.children[i];
    if (!row) continue;
    const p = pts[i];
    const isOk = valid(p);
    row.classList.toggle("selected", i === activeMarkerIndex);
    row.cells[2].textContent = isOk ? "OK" : "Missing";
    row.cells[2].style.color = isOk ? "#59dec3" : "#ef8686";
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
      speed: $("speed") ? $("speed").value : "1"
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
    if (state.speed && $("speed")) $("speed").value = state.speed;

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
  fit();
  measure();
  restoreSessionState(data);
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

// Layout Presets
function setLayout(name) {
  const container = $("windows-container");
  container.className = `layout-${name}`;
  if (name === "dual") {
    $("panel-plot2").hidden = false;
    $("panel-table").hidden = true;
  } else if (name === "full") {
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = false;
  } else if (name === "3d") {
    $("panel-plot1").hidden = true;
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = true;
  } else {
    $("panel-plot1").hidden = false;
    $("panel-plot2").hidden = true;
    $("panel-table").hidden = true;
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
  render();
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
let popoutWindows = {};

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

  const titleText = pane.querySelector(".pane-title") ? pane.querySelector(".pane-title").innerText : paneId;

  const popWin = window.open("", `mkvis3d_popout_${paneId}`, "width=760,height=500,resizable=yes,scrollbars=yes");
  if (!popWin) {
    status("Pop-up bloqueado pelo navegador. Abrindo em janela flutuante interna.");
    floatPane(paneId);
    return;
  }

  popoutWindows[paneId] = popWin;

  const doc = popWin.document;
  doc.open();
  doc.write(`<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mkvis3d — ${titleText}</title>
  <link rel="icon" href="/favicon.ico">
  <style>
    :root {
      --bg-dark: #0e151e; --bg-surface: #141f2d; --bg-panel: #111a24; --bg-panel-alt: #162231;
      --accent: #59dec3; --text: #e4edf5; --text-muted: #8295a8; --border-color: rgba(255, 255, 255, 0.08);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg-dark); color: var(--text);
      display: flex; flex-direction: column; height: 100vh; overflow: hidden;
    }
    .pop-header {
      height: 38px; background: var(--bg-panel-alt); border-bottom: 1px solid var(--border-color);
      display: flex; align-items: center; justify-content: space-between; padding: 0 14px;
      font-size: 12px; font-weight: 600;
    }
    .pop-body { flex: 1; position: relative; overflow: auto; display: flex; }
    .btn-redock {
      background: var(--accent); color: #0b1118; border: none; border-radius: 4px;
      padding: 4px 10px; font-weight: 600; cursor: pointer; font-size: 11px;
    }
    canvas { display: block; width: 100%; height: 100%; }
    .table-wrap { width: 100%; overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
    th { background: var(--bg-surface); position: sticky; top: 0; color: var(--text-muted); }
  </style>
</head>
<body>
  <div class="pop-header">
    <div>● ${titleText} <span style="font-size:10px; color:var(--accent); margin-left:8px;">[Janela Independente]</span></div>
    <div style="display:flex; gap:8px; align-items:center;">
      <span id="pop-readout" style="font-size:11px; color:var(--text-muted);"></span>
      <button class="btn-redock" id="btn-pop-redock">↙ Reanexar à Janela Principal</button>
    </div>
  </div>
  <div class="pop-body" id="pop-body-container"></div>
</body>
</html>`);
  doc.close();

  pane.classList.add("detached-pane");
  const origBody = pane.querySelector(".pane-body");
  let ph = pane.querySelector(`.detached-placeholder`);
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
  if (!popWin || popWin.closed) return;
  const container = popWin.document.getElementById("pop-body-container");
  if (!container) return;

  if (paneId === "panel-plot1" || paneId === "panel-plot2") {
    let popCanvas = popWin.document.getElementById("pop-canvas");
    if (!popCanvas) {
      popCanvas = popWin.document.createElement("canvas");
      popCanvas.id = "pop-canvas";
      container.innerHTML = "";
      container.appendChild(popCanvas);
    }
    const rect = container.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      if (popCanvas.width !== rect.width || popCanvas.height !== rect.height) {
        popCanvas.width = rect.width;
        popCanvas.height = rect.height;
      }
      const popCtx = popCanvas.getContext("2d");
      const srcCanvas = paneId === "panel-plot1" ? $("graph") : $("graph2");
      if (srcCanvas && popCtx && popCanvas.width > 0 && popCanvas.height > 0) {
        popCtx.drawImage(srcCanvas, 0, 0, popCanvas.width, popCanvas.height);
      }
    }
  } else if (paneId === "panel-table") {
    const srcWrap = $("panel-table").querySelector(".table-wrap");
    if (srcWrap) {
      container.innerHTML = `<div class="table-wrap">${srcWrap.innerHTML}</div>`;
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
  if (e.key === "t" || e.key === "T") {
    if ($("trail")) { $("trail").checked = !$("trail").checked; draw(); saveSessionState(); }
  }
  if (e.key === "b" || e.key === "B") {
    if ($("bones")) { $("bones").checked = !$("bones").checked; draw(); saveSessionState(); }
  }
  if (e.key === "d" || e.key === "D") {
    setDistanceVisible(!showDistance);
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

resize();
