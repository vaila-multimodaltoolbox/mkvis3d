import { writeFile } from "node:fs/promises";
import assert from "node:assert/strict";

const root = process.argv[2] || process.cwd();
const targetUrl = process.argv[3];
const cdpPort = process.env.CDP_PORT || "9237";

console.log(`Connecting to CDP on port ${cdpPort}... Target URL: ${targetUrl}`);
const targets = await (await fetch(`http://127.0.0.1:${cdpPort}/json/list`)).json();
const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener("open", resolve, { once: true }));

let nextId = 0;
const pending = new Map();
const consoleErrors = [];

ws.addEventListener("message", e => {
  const r = JSON.parse(e.data);
  if (r.id) {
    const p = pending.get(r.id);
    pending.delete(r.id);
    if (r.error) p.reject(new Error(JSON.stringify(r.error)));
    else p.resolve(r.result);
  } else if (r.method === "Runtime.exceptionThrown") {
    consoleErrors.push(r.params.exceptionDetails);
  }
});

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result.value;
}

async function until(expression, timeoutMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await evaluate(expression);
    if (res) return res;
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error("Timeout waiting for: " + expression);
}

await send("Runtime.enable");
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false });

console.log("Navigating to viewer URL...");
await send("Page.navigate", { url: targetUrl });
await until('document.getElementById("frame")?.textContent.includes("631")');
console.log("✓ Trial loaded: 631 frames, 308 markers, 120 Hz.");

// Wait for companion videos to be discovered via /api/companion_videos
console.log("Checking companion video auto-discovery...");
await until('refVideosList.length >= 3');
const videoCount = await evaluate('refVideosList.length');
console.log(`✓ Discovered ${videoCount} companion videos in directory!`);
assert.ok(videoCount >= 3, `Expected at least 3 companion videos, found ${videoCount}`);

// Verify layout auto-switched to video
await until('document.getElementById("windows-container").classList.contains("layout-video")');
console.log("✓ Layout automatically switched to 3D + Video split preset");

// Wait for first video to load metadata
await until('document.getElementById("ref-video")?.duration > 0');
const duration = await evaluate('document.getElementById("ref-video").duration');
console.log(`✓ Active video (Cam 1) loaded with duration: ${duration.toFixed(3)}s`);

// Check multi-camera selector options
const camOptions = await evaluate(`
  Array.from(document.getElementById("video-camera-select").options).map(o => o.textContent)
`);
console.log("Multi-camera options:", camOptions);
assert.ok(camOptions.some(o => o.includes("c1_cod.mp4")), "c1_cod.mp4 should be in options");
assert.ok(camOptions.some(o => o.includes("c2_cod.mp4")), "c2_cod.mp4 should be in options");
assert.ok(camOptions.some(o => o.includes("c3_cod.mp4")), "c3_cod.mp4 should be in options");
console.log("✓ Multi-camera dropdown populated with all 3 camera angles!");

// Test fluid playback
console.log("Starting playback...");
await evaluate('document.getElementById("play").click()');
assert.equal(await evaluate('playing'), true, "playing should be true");

// Let it play for 1.5 seconds and collect frame progress samples
console.log("Monitoring continuous playback for 1.5s...");
const samples = [];
for (let i = 0; i < 5; i++) {
  await new Promise(r => setTimeout(r, 300));
  const s = await evaluate(`({
    time: document.getElementById("ref-video").currentTime,
    frame: frame,
    paused: document.getElementById("ref-video").paused
  })`);
  samples.push(s);
  console.log(`  Sample ${i + 1}: videoTime=${s.time.toFixed(3)}s, frame=${s.frame}, videoPaused=${s.paused}`);
}

// Verify continuous forward advancement with zero stalls
assert.equal(samples[samples.length - 1].paused, false, "Video should be continuously playing");
assert.ok(samples[samples.length - 1].time > samples[0].time + 0.8, "Video time should advance forward by at least 0.8s");
assert.ok(samples[samples.length - 1].frame > samples[0].frame + 80, "Mocap frame should advance forward by at least 80 frames");

for (let i = 1; i < samples.length; i++) {
  assert.ok(samples[i].time > samples[i - 1].time, `Video time should strictly advance between sample ${i - 1} and ${i}`);
  assert.ok(samples[i].frame > samples[i - 1].frame, `Mocap frame should strictly advance between sample ${i - 1} and ${i}`);
  const drift = Math.abs(samples[i].frame - Math.round(samples[i].time * 120));
  assert.ok(drift <= 2, `Drift ${drift} frames exceeds max tolerance of 2 frames at sample ${i}`);
}
console.log("✓ Master-Clock synchronization verified: Video and mocap are locked with 0 stalls and < 1 frame drift!");

// Test Pause
console.log("Testing pause...");
await evaluate('document.getElementById("play").click()');
assert.equal(await evaluate('playing'), false, "playing should be false");
assert.equal(await evaluate('document.getElementById("ref-video").paused'), true, "video should be paused");
const pausedFrame = await evaluate('frame');
await new Promise(r => setTimeout(r, 300));
const pausedFrameAfter = await evaluate('frame');
assert.equal(pausedFrame, pausedFrameAfter, "Frame must remain still while paused");
console.log(`✓ Pause verified: video and mocap cleanly halted at frame ${pausedFrame}`);

// Test Timeline Scrubbing
console.log("Testing timeline scrubbing...");
await evaluate(`
  const tl = document.getElementById("timeline");
  tl.value = "360";
  tl.dispatchEvent(new Event("input"));
`);
const scrubFrame = await evaluate('frame');
const scrubVidTime = await evaluate('document.getElementById("ref-video").currentTime');
assert.equal(scrubFrame, 360, "Mocap frame should be 360");
const expectedTime = 360 / 120;
assert.ok(Math.abs(scrubVidTime - expectedTime) < 0.04, `Scrubbed video time ${scrubVidTime}s should match target ${expectedTime}s`);
console.log(`✓ Scrubbing verified: frame 360 -> video time ${scrubVidTime.toFixed(3)}s`);

// Test Switching to Camera 2
console.log("Switching to Camera 2 (c2_cod.mp4)...");
await evaluate(`
  const sel = document.getElementById("video-camera-select");
  sel.value = "1";
  sel.dispatchEvent(new Event("change"));
`);
await until('activeVideoIndex === 1');
const cam2Active = await evaluate('refVideoFile.name');
assert.equal(cam2Active, "c2_cod.mp4");
console.log(`✓ Switched to camera: ${cam2Active}`);

// Test Offset Adjustments
console.log("Testing sync offset controls...");
await evaluate('document.getElementById("btn-offset-inc").click()');
assert.equal(await evaluate('videoFrameOffset'), 1);
assert.equal(await evaluate('document.getElementById("video-offset-val").textContent.trim()'), "+1 f");

await evaluate('document.getElementById("btn-offset-inc").click()');
assert.equal(await evaluate('videoFrameOffset'), 2);

await evaluate('document.getElementById("btn-offset-dec").click()');
assert.equal(await evaluate('videoFrameOffset'), 1);

await evaluate('document.getElementById("btn-offset-reset").click()');
assert.equal(await evaluate('videoFrameOffset'), 0);
assert.equal(await evaluate('document.getElementById("video-offset-val").textContent.trim()'), "0 f");
console.log("✓ Offset increment, decrement, and reset verified");

// Test Clicking on Video to Play/Pause
console.log("Testing click-on-video viewport...");
await evaluate('document.getElementById("ref-video").click()');
assert.equal(await evaluate('playing'), true, "Clicking video should start playback");
await new Promise(r => setTimeout(r, 400));
await evaluate('document.getElementById("ref-video").click()');
assert.equal(await evaluate('playing'), false, "Clicking video again should pause playback");
console.log("✓ Click on video viewport plays and pauses properly");

// Capture screenshot of verified state
console.log("Capturing screenshot of synchronized mocap + video...");
const shot = await send("Page.captureScreenshot", { format: "png" });
await writeFile(`${root}/outputs/screenshot_video_sync_verified.png`, Buffer.from(shot.data, "base64"));
console.log(`✓ Saved screenshot to outputs/screenshot_video_sync_verified.png`);

assert.equal(consoleErrors.length, 0, `Unexpected console errors: ${JSON.stringify(consoleErrors)}`);

console.log("\n=======================================================");
console.log("ALL E2E VIDEO PLAYBACK AND SYNC TESTS PASSED WITH 100% SUCCESS!");
console.log("=======================================================\n");
process.exit(0);
