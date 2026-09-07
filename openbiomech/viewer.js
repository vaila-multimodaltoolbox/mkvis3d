"use strict";
const $ = id => document.getElementById(id);
const boot = JSON.parse($("trial-data").textContent);
const token = location.hash.slice(1);

let trial = null, frame = 0, playing = false, lastTick = 0, elapsed = 0;
let yaw = -0.45, pitch = 0.22, zoom = 1, pan = [0, 0], center = [0, 0, 0], span = 1;
let distances = [], activeMarkerIndex = 0;
let skeletonPairs = [];

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
  for (const points of trial.xyz) {
    for (const raw of points) {
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

// Skeleton / Bone connections
function initSkeleton(labels) {
  skeletonPairs = [];
  const map = new Map(labels.map((lbl, idx) => [lbl, idx]));

  // Standard squat pairs
  const squatPairs = [
    ["D_barra2", "D_barra1"], ["D_barra1", "barra_centro"],
    ["barra_centro", "E_barra1"], ["E_barra1", "E_barra2"],
    ["D_trocanter", "D_joelho"], ["D_joelho", "D_tornozelo"],
    ["E_trocanter", "E_joelho"], ["E_joelho", "E_tornozelo"],
    ["D_trocanter", "E_trocanter"],
    ["D_acromio", "E_acromio"],
    ["D_acromio", "D_trocanter"], ["E_acromio", "E_trocanter"],
    ["D_acromio", "D_mao"], ["E_acromio", "E_mao"]
  ];
  for (const [a, b] of squatPairs) {
    if (map.has(a) && map.has(b)) {
      skeletonPairs.push([map.get(a), map.get(b)]);
    }
  }

  // Automatic distance-based pairs if no known markers
  if (skeletonPairs.length === 0 && trial && trial.xyz[0]) {
    const pts = trial.xyz[0];
    for (let i = 0; i < pts.length; i++) {
      if (!valid(pts[i])) continue;
      for (let j = i + 1; j < pts.length; j++) {
        if (!valid(pts[j])) continue;
        const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1], pts[i][2] - pts[j][2]);
        if (d > 0.05 && d < 0.22) {
          skeletonPairs.push([i, j]);
        }
      }
    }
  }
}

function drawSkeleton(pts) {
  if (!$("bones") || !$("bones").checked || !skeletonPairs.length) return;
  for (const [i, j] of skeletonPairs) {
    if (valid(pts[i]) && valid(pts[j])) {
      line(pts[i], pts[j], "rgba(110, 160, 205, 0.7)", 2);
    }
  }
}

// 3D Scene Rendering
function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);
  if (!trial) return;

  drawGroundGrid();

  const pts = trial.xyz[frame];
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
  if ($("trail") && $("trail").checked && activeIdx >= 0) {
    for (let f = Math.max(1, frame - 120); f <= frame; f++) {
      const p = trial.xyz[f - 1][activeIdx], q = trial.xyz[f][activeIdx];
      if (valid(p) && valid(q)) line(p, q, "#35827c", 1.5);
    }
  }

  // Distance line between Marker A and B
  if (valid(pts[a]) && valid(pts[b])) line(pts[a], pts[b], "#f2c875", 2);

  // Render Marker Points
  const visible = pts.map((p, i) => ({ p, i })).filter(v => valid(v.p)).map(v => ({ ...v, q: project(v.p) })).sort((a, b) => b.q[2] - a.q[2]);

  for (const { i, q } of visible) {
    const isAct = i === activeIdx;
    const isA = i === a, isB = i === b;
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
    $("distance").textContent = Number.isFinite(d) ? `${d.toFixed(4)} m` : "Missing";
  }

  // Draw charts and update table
  drawPlot1();
  drawPlot2();
  updateTable();
}

// Primary Plot (Plot 1)
function drawPlot1() {
  const canvasG = graph1;
  const gx = gx1;
  const mode = $("plot1-mode") ? $("plot1-mode").value : "distance";
  drawSinglePlot(canvasG, gx, mode, $("plot1-readout"));
}

// Secondary Plot (Plot 2)
function drawPlot2() {
  if (!graph2 || !$("panel-plot2") || $("panel-plot2").hidden) return;
  const canvasG = $("graph2");
  const gx = graph2;
  const mode = $("plot2-mode") ? $("plot2-mode").value : "active-z";
  drawSinglePlot(canvasG, gx, mode, $("plot2-readout"));
}

function drawSinglePlot(canvasG, gx, mode, readoutEl) {
  const w = canvasG.clientWidth, h = canvasG.clientHeight;
  gx.clearRect(0, 0, w, h);
  if (!trial) return;

  let series = []; // array of { name, color, values }
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

  // Find min and max across all series
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

  // Update live readout text
  if (readoutEl) {
    const curVals = series.map(s => {
      const v = s.values[frame];
      return `${s.name}: ${Number.isFinite(v) ? v.toFixed(3) : "—"}`;
    }).join("  |  ");
    readoutEl.textContent = curVals;
  }

  // Draw horizontal guide lines
  gx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  gx.lineWidth = 1;
  for (let k = 0; k <= 3; k++) {
    const y = 14 + k * (h - 28) / 3;
    gx.beginPath();
    gx.moveTo(50, y);
    gx.lineTo(w - 10, y);
    gx.stroke();
  }

  // Draw plot series curves
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

  // Value range axis labels
  gx.fillStyle = "#8298ad";
  gx.font = "10px system-ui, sans-serif";
  gx.fillText(`${hi.toFixed(3)}`, 2, 14);
  gx.fillText(`${lo.toFixed(3)}`, 2, h - 10);

  // Draw Playhead Cursor Line
  const curX = 50 + frame * (w - 65) / Math.max(1, totalFrames - 1);
  gx.strokeStyle = "#f2c875";
  gx.lineWidth = 1.5;
  gx.beginPath();
  gx.moveTo(curX, 0);
  gx.lineTo(curX, h);
  gx.stroke();
}

// Marker Inspector Table
function updateTable() {
  if (!$("panel-table") || $("panel-table").hidden || !trial) return;
  const tbody = $("marker-table-body");
  if (!tbody) return;
  const pts = trial.xyz[frame];
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
}

function seekToMotion() {
  if (!trial) return;
  pause();
  // Find frame where standard deviation or motion begins
  let motionFrame = 0;
  const pts0 = trial.xyz[0];
  for (let f = 1; f < trial.xyz.length; f++) {
    let diffSum = 0;
    for (let m = 0; m < trial.labels.length; m++) {
      const p = pts0[m], q = trial.xyz[f][m];
      if (valid(p) && valid(q)) diffSum += Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
    }
    if (diffSum / trial.labels.length > 0.04) { // moved > 4cm on average
      motionFrame = Math.max(0, f - 10);
      break;
    }
  }
  frame = motionFrame;
  draw();
  status(`Jumped to motion onset at frame ${frame + 1} (${(frame / trial.rate_hz).toFixed(2)}s).`);
}

function load(data) {
  trial = data;
  frame = 0;
  pause();
  activeMarkerIndex = 0;

  $("title").textContent = data.name;
  $("meta").textContent = `${data.xyz.length} frames · ${data.labels.length} markers · ${data.rate_hz} Hz · coordinates in meters`;
  if ($("marker-count-badge")) $("marker-count-badge").textContent = `${data.labels.length} markers`;
  $("welcome").hidden = true;

  // Populate Marker Selectors
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

  // Enable controls
  for (const id of ["play", "prev", "next", "timeline", "export", "snapshot", "first", "last", "seek-motion"]) {
    if ($(id)) $(id).disabled = false;
  }
  $("timeline").max = String(data.xyz.length - 1);

  initSkeleton(data.labels);
  buildTable();
  fit();
  measure();
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
    if (frame === trial.xyz.length - 1) frame = 0;
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
}
$("prev").onclick = () => step(-1);
$("next").onclick = () => step(1);
if ($("first")) $("first").onclick = () => { pause(); frame = 0; draw(); };
if ($("last")) $("last").onclick = () => { pause(); frame = trial.xyz.length - 1; draw(); };
if ($("seek-motion")) $("seek-motion").onclick = seekToMotion;

$("timeline").oninput = () => {
  pause();
  frame = Number($("timeline").value);
  draw();
};

function tick(now) {
  if (playing && trial) {
    elapsed += (now - lastTick) / 1000 * trial.rate_hz * Number($("speed").value);
    const advance = Math.floor(elapsed);
    elapsed -= advance;
    if (advance) {
      frame += advance;
      if (frame >= trial.xyz.length) {
        if ($("loop").checked) frame %= trial.xyz.length;
        else {
          frame = trial.xyz.length - 1;
          pause();
        }
      }
      draw();
    }
  }
  lastTick = now;
  requestAnimationFrame(tick);
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
};
canvas.onpointerup = () => drag = null;
canvas.onpointercancel = () => drag = null;
canvas.onwheel = e => {
  e.preventDefault();
  zoom = Math.max(0.1, Math.min(20, zoom * Math.exp(-e.deltaY * 0.001)));
  draw();
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
  };
}
setupChartSeek(graph1);
if ($("graph2")) setupChartSeek($("graph2"));

// Camera View Presets
$("front").onclick = () => { yaw = 0; pitch = 0; draw(); };
$("side").onclick = () => { yaw = Math.PI / 2; pitch = 0; draw(); };
$("top").onclick = () => { yaw = 0; pitch = Math.PI / 2; draw(); };
$("reset").onclick = fit;

if ($("up")) $("up").onchange = fit;
for (const id of ["labels", "trail", "grid", "bones"]) {
  if ($(id)) $(id).onchange = draw;
}
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
  } else { // default
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

// Help Modal
if ($("action-help-shortcuts")) {
  $("action-help-shortcuts").onclick = () => $("modal-shortcuts").classList.add("open");
}
if ($("action-help-about")) {
  $("action-help-about").onclick = () => {
    alert("mkvis3d · OpenBiomech\nModern biomechanical motion viewer & analysis suite\nEngineered for Vicon, Qualisys, C3D, CSV, and .3d formats.");
  };
}

// Keyboard shortcuts
document.addEventListener("keydown", e => {
  if (["INPUT", "SELECT", "BUTTON", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); $("play").click(); }
  if (e.code === "ArrowLeft") step(-1);
  if (e.code === "ArrowRight") step(1);
  if (e.code === "Home") { e.preventDefault(); if ($("first")) $("first").click(); }
  if (e.code === "End") { e.preventDefault(); if ($("last")) $("last").click(); }
  if (e.key === "r" || e.key === "R") fit();
  if (e.key === "g" || e.key === "G") {
    if ($("grid")) { $("grid").checked = !$("grid").checked; draw(); }
  }
  if (e.key === "l" || e.key === "L") {
    if ($("labels")) { $("labels").checked = !$("labels").checked; draw(); }
  }
  if (e.key === "t" || e.key === "T") {
    if ($("trail")) { $("trail").checked = !$("trail").checked; draw(); }
  }
  if (e.key === "b" || e.key === "B") {
    if ($("bones")) { $("bones").checked = !$("bones").checked; draw(); }
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
if (boot.trial) load(boot.trial);
resize();
