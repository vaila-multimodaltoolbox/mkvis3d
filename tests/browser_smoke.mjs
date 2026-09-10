import {writeFile, mkdir} from "node:fs/promises";
import assert from "node:assert/strict";
import { resolve } from "node:path";
const root = resolve(process.argv[2] || process.cwd());
const outputDir = process.env.SMOKE_OUTPUT_DIR || resolve(root, "outputs");
await mkdir(outputDir, {recursive:true});
const cdpPort = process.env.CDP_PORT || "9237";
const targets=await (await fetch("http://127.0.0.1:"+cdpPort+"/json/list")).json();
const ws=new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
await new Promise(resolve=>ws.addEventListener("open",resolve,{once:true}));
let next=0;const pending=new Map(),errors=[];
ws.addEventListener("message",e=>{
  const r=JSON.parse(e.data);
  if(r.method==="Page.javascriptDialogOpening"){
    send("Page.handleJavaScriptDialog",{accept:true,promptText:r.params.defaultPrompt||""}).catch(()=>{});
  }
  if(r.id){const p=pending.get(r.id);pending.delete(r.id);if(r.error)p.reject(new Error(JSON.stringify(r.error)));else p.resolve(r.result);}else if(r.method==="Runtime.exceptionThrown")errors.push(r.params.exceptionDetails);
});
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw new Error("Timeout: "+expression);}
await send("Runtime.enable");await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride",{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
await send("Page.navigate",{url:"file://"+outputDir+"/rec3d_viewer.html"});
await until('document.getElementById("frame")?.textContent.includes("631")');
assert.match(await evaluate('document.getElementById("meta").textContent'),/70 markers|70 marcadores/);
assert.equal(await evaluate('document.getElementById("open-panel").hidden'),true);

// Navigation ownership, defaults, and device-only sidebar preference.
assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".menu-item")).map(e => e.id)'),
  ["menu-file", "menu-view", "menu-analysis", "menu-windows", "menu-help"]);
assert.equal(await evaluate('document.getElementById("plot1-mode").value'), "active-xyz");
assert.equal(await evaluate('document.getElementById("plot1-mode").selectedOptions[0].textContent'), "Active Markers X, Y, Z");
assert.equal(await evaluate('document.getElementById("plot2-mode").value'), "active-z");
assert.equal(await evaluate('document.getElementById("sidebar").hidden'), false);
assert.equal(await evaluate('document.querySelector("#sidebar #btn-open-kinematics, #sidebar #btn-open-lcs, #menu-options")'), null);
for (const [menu, actions] of Object.entries({
  file: ["btn-attach-analysis", "file-analysis", "action-export-kinematics-csv", "action-export-kinematics-py", "action-import-replace-marker-csv"],
  view: ["action-cycle-marker-color", "action-toggle-loop", "action-theme-dark"],
  analysis: ["action-view-lcs", "action-view-filter", "action-kinematics-modal", "action-kinematics-virtual-pts", "action-kinematics-live-tab", "action-kinematics-plot-euler"],
  windows: ["action-win-sidebar", "action-float-plot1", "action-win-select-points", "preset-dual"],
  help: ["action-help-manual", "action-help-theory", "action-help-shortcuts", "action-help-about", "action-help-github"]
})) {
  for (const id of actions) assert.equal(await evaluate(`document.getElementById(${JSON.stringify(id)}).closest('.menu-item').id`), "menu-" + menu);
}
assert.deepEqual(await evaluate(`(() => {
  const ids = Array.from(document.querySelectorAll('[id]')).map(e => e.id);
  return ids.filter((id, i) => ids.indexOf(id) !== i);
})()`), []);
const expandedWidth = await evaluate('document.getElementById("workspace").clientWidth');
const sidebarWidth = await evaluate('document.getElementById("sidebar").getBoundingClientRect().width');
await evaluate('document.getElementById("marker-select").focus(); setSidebarVisible(false)');
assert.equal(await evaluate('document.activeElement.id'), "btn-toggle-sidebar");
assert.equal(await evaluate('document.getElementById("sidebar").inert'), true);
assert.equal(await evaluate('document.getElementById("action-win-sidebar").getAttribute("aria-expanded")'), "false");
assert.equal(await evaluate('document.getElementById("workspace").clientWidth'), expandedWidth + sidebarWidth);
await until('document.getElementById("scene").width === Math.round(document.getElementById("scene").clientWidth * devicePixelRatio)');
await evaluate('document.getElementById("marker-select").focus()');
assert.equal(await evaluate('document.activeElement.id'), "btn-toggle-sidebar");
// Real Tab presses must skip every hidden sidebar control, and wrap back to the toggle.
let reachedToggle = false;
for (let i = 0; i < 100; i++) {
  await send("Input.dispatchKeyEvent", {type:"keyDown", key:"Tab", code:"Tab", windowsVirtualKeyCode:9});
  await send("Input.dispatchKeyEvent", {type:"keyUp", key:"Tab", code:"Tab", windowsVirtualKeyCode:9});
  assert.equal(await evaluate('document.getElementById("sidebar").contains(document.activeElement)'), false);
  if (await evaluate('document.activeElement.id === "btn-toggle-sidebar"')) { reachedToggle = true; break; }
}
assert.ok(reachedToggle, "sidebar toggle remains in the keyboard cycle");
await send("Page.reload");
await until('document.getElementById("frame")?.textContent.includes("631")');
assert.equal(await evaluate('document.getElementById("sidebar").hidden'), true);
await evaluate('document.getElementById("action-win-sidebar").click()');
assert.equal(await evaluate('document.getElementById("btn-toggle-sidebar").getAttribute("aria-expanded")'), "true");
assert.equal(await evaluate('localStorage.getItem("mkvis3d_sidebar_visible")'), "true");
assert.equal(await evaluate('Object.keys(collectViewerState()).some(k => /sidebar/i.test(k))'), false);

// A blocked storage getter must not interrupt startup or either toggle direction.
const storageFailure = await send("Page.addScriptToEvaluateOnNewDocument", {source:`
  Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError');}});
`});
await send("Page.reload");
await until('document.getElementById("frame")?.textContent.includes("631")');
assert.equal(await evaluate('document.getElementById("sidebar").hidden'), false);
await evaluate('document.getElementById("btn-toggle-sidebar").click()');
assert.equal(await evaluate('document.getElementById("sidebar").hidden'), true);
await evaluate('document.getElementById("action-win-sidebar").click()');
assert.equal(await evaluate('document.getElementById("sidebar").hidden'), false);
await send("Page.removeScriptToEvaluateOnNewDocument", {identifier:storageFailure.identifier});
await send("Page.reload");
await until('document.getElementById("frame")?.textContent.includes("631")');

// Exercise moved actions, including the real destinations of virtual/live tabs.
for (const [action, tab] of [["action-kinematics-modal", "bases"], ["action-kinematics-virtual-pts", "points"], ["action-kinematics-live-tab", "kinematics"], ["action-export-kinematics-py", "export"]]) {
  await evaluate(`document.getElementById('${action}').click()`);
  assert.equal(await evaluate(`document.getElementById('tab-content-${tab}').hidden`), false);
  await evaluate('document.getElementById("btn-close-kinematics").click()');
}
for (const [action, modal, close] of [["action-view-lcs", "modal-lcs", "btn-close-lcs"], ["action-view-filter", "modal-filter", "btn-close-filter"]]) {
  await evaluate(`document.getElementById('${action}').click()`);
  assert.equal(await evaluate(`document.getElementById('${modal}').hidden`), false);
  await evaluate(`document.getElementById('${close}').click()`);
}
assert.equal(await evaluate(`(() => {
  const input = document.getElementById('file-analysis'); let clicked = false;
  const original = input.click; input.click = () => { clicked = true; };
  document.getElementById('btn-attach-analysis').click(); input.click = original;
  return clicked;
})()`), true);

// Theme Verification: default dark mode
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");
assert.equal(await evaluate('document.getElementById("theme-label").textContent'), "Dark");
assert.equal(await evaluate('document.getElementById("theme-icon").textContent'), "🌙");

// Switch to Light Mode via toolbar button
await evaluate('document.getElementById("btn-toggle-theme").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "light");
assert.equal(await evaluate('document.getElementById("theme-label").textContent'), "Light");
assert.equal(await evaluate('document.getElementById("theme-icon").textContent'), "☀️");

// Capture Light Mode screenshot
const lightShot = await send("Page.captureScreenshot", { format: "png" });
await writeFile(outputDir + "/viewer_light.png", Buffer.from(lightShot.data, "base64"));

// Switch to Dark Mode via View menu
await evaluate('document.getElementById("action-theme-dark").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");

// Switch to Light Mode via View menu
await evaluate('document.getElementById("action-theme-light").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "light");

// Toggle with Alt+T shortcut (light -> dark)
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", altKey: true, bubbles: true }))');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");

// Toggle with Alt+T shortcut (dark -> light)
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", altKey: true, bubbles: true }))');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "light");

// Return to dark mode for baseline tests
await evaluate('document.getElementById("btn-toggle-theme").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");

// Inspect both themes, sidebar states, and every layout at the requested sizes.
for (const [width, height] of [[1440, 1050], [1024, 768]]) {
  await send("Emulation.setDeviceMetricsOverride", {width, height, deviceScaleFactor:1, mobile:false});
  for (const theme of ["dark", "light"]) {
    for (const visible of [true, false]) {
      await evaluate(`setTheme('${theme}'); setSidebarVisible(${visible})`);
      for (const layout of ["default", "dual", "full", "video", "3d"]) {
        await evaluate(`document.getElementById('preset-${layout}').click()`);
        await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
        const geometry = await evaluate(`(() => {
          const workspace = document.getElementById('workspace').getBoundingClientRect();
          const panes = Array.from(document.querySelectorAll('#windows-container > .window-pane')).filter(e => !e.hidden);
          return panes.map(pane => {
            const r = pane.getBoundingClientRect();
            const c = pane.querySelector('canvas');
            return {id:pane.id, inside:r.right <= workspace.right + 1 && r.bottom <= workspace.bottom + 1,
              width:r.width, height:r.height, canvasHeight:c?.clientHeight ?? 100,
              headerFits:pane.querySelector('.pane-header').scrollWidth <= r.width + 1};
          });
        })()`);
        for (const pane of geometry) {
          const context = JSON.stringify({width, height, theme, visible, layout, pane});
          assert.ok(pane.inside && pane.width > 50 && pane.height > 40, context);
          assert.ok(pane.canvasHeight > 50, context);
          assert.ok(pane.headerFits, context);
        }
        assert.ok(await evaluate('document.getElementById("btn-toggle-sidebar").getBoundingClientRect().right <= innerWidth'));
        if (["default", "dual"].includes(layout)) {
          const shot = await send("Page.captureScreenshot", {format:"png"});
          await writeFile(`${outputDir}/layout-${width}-${theme}-${visible ? "expanded" : "collapsed"}-${layout}.png`, Buffer.from(shot.data, "base64"));
        }
      }
      await evaluate('document.getElementById("preset-default").click()');
      for (const [action, modal, close] of [["action-view-lcs", "modal-lcs", "btn-close-lcs"], ["action-view-filter", "modal-filter", "btn-close-filter"], ["action-kinematics-modal", "modal-kinematics", "btn-close-kinematics"]]) {
        await evaluate(`document.getElementById('${action}').click()`);
        assert.ok(await evaluate(`(() => {
          const modal = document.getElementById('${modal}'); const r = modal.getBoundingClientRect();
          const close = document.getElementById('${close}').getBoundingClientRect();
          return !modal.hidden && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight && close.right <= innerWidth;
        })()`), `${width} ${theme} ${modal} bounds`);
        await evaluate(`document.getElementById('${close}').click()`);
      }
      await evaluate('document.getElementById("action-float-plot1").click()');
      assert.equal(await evaluate('activeFloatingPanes.has("panel-plot1")'), true);
      assert.ok(await evaluate('document.getElementById("graph").clientHeight > 20'));
      await evaluate('document.getElementById("action-dock-all").click()');
    }
    for (const menu of ["file", "view", "analysis", "windows", "help"]) {
      await evaluate(`document.querySelector('#menu-${menu} > .menu-btn').click()`);
      assert.ok(await evaluate(`(() => {const r = document.querySelector('#menu-${menu} .dropdown-menu').getBoundingClientRect(); return r.right <= innerWidth && r.bottom <= innerHeight;})()`), `${width} ${menu} menu bounds`);
      await evaluate('closeMenus()');
    }
  }
}
await send("Emulation.setDeviceMetricsOverride", {width:1440, height:1050, deviceScaleFactor:1, mobile:false});
await evaluate('setTheme("dark"); setSidebarVisible(true); setLayout("default"); document.activeElement.blur()');

assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".dropdown-item")).filter(e => !e.hidden && !e.onclick).map(e => e.id || e.textContent)'), []);

// Retained View actions update their scene state and keyboard shortcuts still work.
await evaluate('document.querySelector("[data-up=y]").click()');
assert.equal(await evaluate('document.getElementById("up").value'), "y");
await evaluate('document.querySelector("[data-up=z]").click()');
await evaluate('document.querySelector("[data-floor=origin]").click()');
assert.equal(await evaluate('getFloorHeight()'), 0);
await evaluate('document.querySelector("[data-floor=auto]").click()');
await evaluate('document.getElementById("action-toggle-axes").click()');
assert.equal(await evaluate('showLabAxes'), false);
await evaluate('document.getElementById("action-toggle-axes").click()');
for (const [action, control] of [["action-toggle-grid", "grid"], ["action-toggle-labels", "labels"], ["action-toggle-trails", "trail"], ["action-toggle-bones", "bones"], ["action-toggle-loop", "loop"]]) {
  const before = await evaluate(`document.getElementById('${control}').checked`);
  await evaluate(`document.getElementById('${action}').click()`);
  assert.equal(await evaluate(`document.getElementById('${control}').checked`), !before);
  await evaluate(`document.getElementById('${action}').click()`);
}
for (const [key, modal, close] of [["k", "modal-kinematics", "btn-close-kinematics"], ["l", "modal-lcs", "btn-close-lcs"], ["f", "modal-filter", "btn-close-filter"]]) {
  await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', {key:'${key}', altKey:true, bubbles:true}))`);
  assert.equal(await evaluate(`document.getElementById('${modal}').hidden`), false);
  await evaluate(`document.getElementById('${close}').click()`);
}

// Marker Size & Color Customization verification (viewc3d.py parity)
assert.equal(await evaluate('markerSize'), 3.5);
assert.equal(await evaluate('markerColor'), "auto");

// Test '+' and '-' keyboard shortcuts for marker size
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "+", bubbles: true }))');
assert.equal(await evaluate('markerSize'), 4.0);
assert.equal(await evaluate('document.getElementById("marker-size-val").textContent'), "4.0 px");

await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "-", bubbles: true }))');
assert.equal(await evaluate('markerSize'), 3.5);

// Test marker size slider
await evaluate('document.getElementById("marker-size-slider").value = "5"; document.getElementById("marker-size-slider").dispatchEvent(new Event("input"))');
assert.equal(await evaluate('markerSize'), 5.0);

// Test 'C' shortcut to cycle marker colors (11 colors from viewc3d.py)
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "c", bubbles: true }))');
assert.equal(await evaluate('markerColor'), "#f97316"); // Orange (viewc3d default)
assert.equal(await evaluate('document.getElementById("marker-color-name-badge").textContent'), "Orange");

// Test swatch selection (Green)
await evaluate('document.querySelector(".color-swatch-btn[data-color=\\"#22c55e\\"]").click()');
assert.equal(await evaluate('markerColor'), "#22c55e");
assert.equal(await evaluate('document.getElementById("marker-color-name-badge").textContent'), "Green");

// Test reset button
await evaluate('document.getElementById("btn-reset-marker-style").click()');
assert.equal(await evaluate('markerColor'), "auto");
assert.equal(await evaluate('markerSize'), 3.5);

// Test Skeleton Color Palette
assert.equal(await evaluate('skeletonColor'), "auto");
assert.equal(await evaluate('document.getElementById("skeleton-color-name-badge").textContent.toLowerCase()'), "default");
await evaluate('document.querySelector("#skeleton-color-swatches .color-swatch-btn[data-color=\\"#3b82f6\\"]").click()');
assert.equal(await evaluate('skeletonColor'), "#3b82f6");
assert.equal(await evaluate('document.getElementById("skeleton-color-name-badge").textContent'), "Blue");
assert.equal(await evaluate('document.querySelector("#skeleton-color-swatches .color-swatch-btn[data-color=\\"#3b82f6\\"]").classList.contains("selected")'), true);
await evaluate('document.getElementById("btn-reset-skeleton-style").click()');
assert.equal(await evaluate('skeletonColor'), "auto");
assert.equal(await evaluate('document.getElementById("skeleton-color-name-badge").textContent.toLowerCase()'), "default");

// Test Viewport Mode Controls: default is now "rotate"
assert.equal(await evaluate('viewportMode'), "rotate");
assert.equal(await evaluate('document.getElementById("btn-mode-rotate").classList.contains("active")'), true);
await evaluate('document.getElementById("btn-mode-select").click()');
assert.equal(await evaluate('viewportMode'), "select");
assert.equal(await evaluate('document.getElementById("btn-mode-select").classList.contains("active")'), true);
await evaluate('document.getElementById("btn-mode-pan").click()');
assert.equal(await evaluate('viewportMode'), "pan");
assert.equal(await evaluate('document.getElementById("btn-mode-pan").classList.contains("active")'), true);
await evaluate('document.getElementById("btn-mode-rotate").click()');
assert.equal(await evaluate('viewportMode'), "rotate");
assert.equal(await evaluate('document.getElementById("btn-mode-rotate").classList.contains("active")'), true);

// Test Quick Smooth Filter Cutoff input
assert.equal(await evaluate('document.getElementById("quick-filter-cutoff").value'), "6");
await evaluate('document.getElementById("quick-filter-cutoff").value = "8.0"; document.getElementById("quick-filter-cutoff").dispatchEvent(new Event("change"))');
assert.equal(await evaluate('quickFilterCutoff'), 8.0);
await evaluate('document.getElementById("btn-quick-filter").click()');
assert.equal(await evaluate('activeFilterConfig.cutoff'), 8.0);
await evaluate('document.getElementById("btn-revert-filter").click()');
assert.equal(await evaluate('activeFilterConfig'), null);

// Test Angles starting disabled / hidden, and Absolute Angle mode
assert.equal(await evaluate('showAngle'), false);
assert.equal(await evaluate('document.getElementById("chk-show-angle").checked'), false);
assert.equal(await evaluate('document.getElementById("txt-show-angle").textContent'), "Hidden");
assert.equal(await evaluate('document.getElementById("btn-toggle-angle").textContent'), "Enable");
await evaluate('document.getElementById("btn-angle-mode-abs").click()');
assert.equal(await evaluate('angleMode'), "abs");
assert.equal(await evaluate('document.getElementById("angle-abs-container").style.display'), "block");
assert.equal(await evaluate('document.getElementById("btn-angle-mode-abs").classList.contains("active")'), true);
await evaluate('document.getElementById("btn-toggle-angle").click()');
assert.equal(await evaluate('showAngle'), true);
assert.ok(await evaluate('Number.isFinite(angles[frame])'));
await evaluate('document.getElementById("btn-toggle-angle").click()');
await evaluate('document.getElementById("btn-angle-mode-3pt").click()');

// Test Pin / Mark Selected Points
await evaluate('setSelectedMarkers([0, 1])');
await evaluate('document.getElementById("btn-points-pin-selected").click()');
assert.equal(await evaluate('pinnedMarkerIndices.has(0) && pinnedMarkerIndices.has(1)'), true);
await evaluate('document.getElementById("btn-points-pin-selected").click()');
assert.equal(await evaluate('pinnedMarkerIndices.has(0) || pinnedMarkerIndices.has(1)'), false);

// Test Segment Creation from Selected Markers (Context Menu Action / K hotkey)
const initialBones = await evaluate('skeletonPairs.length');
await evaluate('setSelectedMarkers([2, 5])');
await evaluate('createSegmentFromSelected()');
assert.equal(await evaluate('skeletonPairs.length'), initialBones + 1);
assert.equal(await evaluate('document.getElementById("bones").checked'), true);

// Test Single-Key Shortcuts: A, P, M, S, K, E
await evaluate('if (document.activeElement) document.activeElement.blur()');
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }))');
assert.equal(await evaluate('showAngle'), true);
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }))');
assert.equal(await evaluate('showAngle'), false);

await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "p", bubbles: true }))');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), false);
await evaluate('if (document.activeElement) document.activeElement.blur()');
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "p", bubbles: true }))');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), true);

// Test Vertical Splitter between 3D Viewport and Charts
assert.ok(await evaluate('Boolean(document.getElementById("vertical-splitter"))'));
await evaluate('document.getElementById("windows-container").style.setProperty("--plot-height", "220px"); resize()');
assert.equal(await evaluate('getComputedStyle(document.getElementById("windows-container")).getPropertyValue("--plot-height").trim()'), "220px");

// Capture screenshot demonstrating custom orange markers + resized vertical splitter
await evaluate('setMarkerColor("#f97316", "Orange"); setMarkerSize(5.0);');
const markerShot = await send("Page.captureScreenshot", { format: "png" });
await writeFile(outputDir + "/viewer_custom_markers.png", Buffer.from(markerShot.data, "base64"));

await evaluate('document.getElementById("vertical-splitter").dispatchEvent(new MouseEvent("dblclick", { bubbles: true }))');
assert.equal(await evaluate('getComputedStyle(document.getElementById("windows-container")).getPropertyValue("--plot-height").trim()'), "170px");
await evaluate('resetMarkerStyle();');

// Test Popout subwindow and graceful floating fallback under headless browser
await evaluate('document.querySelector(".btn-popout[data-pane=\\"panel-plot1\\"]").click()');
const isPoppedOrFloated = await evaluate('Boolean(popoutWindows["panel-plot1"] || activeFloatingPanes.has("panel-plot1"))');
assert.ok(isPoppedOrFloated);
await evaluate('dockAllPanes()');
assert.equal(await evaluate('activeFloatingPanes.has("panel-plot1")'), false);

// Test simulated popout subwindow rendering and redocking
await evaluate(`
  const mockDoc = document.implementation.createHTMLDocument("popout");
  mockDoc.body.innerHTML = '<div class="pop-header"><button id="btn-pop-redock">Reanexar</button></div><div id="pop-body-container"></div>';
  popoutWindows["panel-plot1"] = {
    document: mockDoc,
    closed: false,
    focus: () => {},
    close: () => {},
    addEventListener: () => {}
  };
  document.getElementById("panel-plot1").classList.add("detached-pane");
  syncPopoutContent("panel-plot1");
`);
assert.ok(await evaluate('Boolean(popoutWindows["panel-plot1"])'));
assert.equal(await evaluate('document.getElementById("panel-plot1").classList.contains("detached-pane")'), true);
await evaluate('restorePoppedOutPane("panel-plot1")');
assert.equal(await evaluate('document.getElementById("panel-plot1").classList.contains("detached-pane")'), false);
assert.equal(await evaluate('Boolean(popoutWindows["panel-plot1"])'), false);

// Test Select Points Modal & WAI-ARIA APG Listbox
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), true);
await evaluate('document.getElementById("btn-open-select-points").click()');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), false);
assert.equal(await evaluate('document.querySelectorAll("#points-listbox .point-option").length'), 70);

// Test Search filter
await evaluate('{ const s = document.getElementById("points-search-input"); s.value = "HEEL"; s.dispatchEvent(new Event("input")); }');
assert.ok(await evaluate('document.querySelectorAll("#points-listbox .point-option").length < 70'));
await evaluate('{ const s = document.getElementById("points-search-input"); s.value = ""; s.dispatchEvent(new Event("input")); }');
assert.equal(await evaluate('document.querySelectorAll("#points-listbox .point-option").length'), 70);

// Test Select All and Unselect All
await evaluate('document.getElementById("btn-points-select-all").click()');
assert.equal(await evaluate('selectedMarkerIndices.size'), 70);
assert.match(await evaluate('document.getElementById("points-selection-count").textContent'), /70 of 70/);
await evaluate('document.getElementById("btn-points-unselect-all").click()');
assert.equal(await evaluate('selectedMarkerIndices.size'), 0);
assert.match(await evaluate('document.getElementById("points-selection-count").textContent'), /0 of 70/);

// Test single selection via listbox item click
await evaluate('document.querySelector("#points-listbox .point-option[data-index=\\"0\\"]").click()');
assert.equal(await evaluate('selectedMarkerIndices.size'), 1);
assert.equal(await evaluate('selectedMarkerIndices.has(0)'), true);
assert.equal(await evaluate('activeMarkerIndex'), 0);

// Test closing modal via Escape
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), true);

// Test opening modal via menu action and closing via close button
await evaluate('document.getElementById("action-win-select-points").click()');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), false);
await evaluate('document.getElementById("btn-close-points").click()');
assert.equal(await evaluate('document.getElementById("modal-points").hidden'), true);

// Test Frame Playback Shortcuts (Arrows ±1 and ±60)
await evaluate('if (document.activeElement) document.activeElement.blur()');
const startFrame = await evaluate('frame');
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowRight", key: "ArrowRight", bubbles: true }))');
assert.equal(await evaluate('frame'), startFrame + 1);
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowLeft", key: "ArrowLeft", bubbles: true }))');
assert.equal(await evaluate('frame'), startFrame);
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowUp", key: "ArrowUp", bubbles: true }))');
assert.equal(await evaluate('frame'), startFrame + 60);
await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowDown", key: "ArrowDown", bubbles: true }))');
assert.equal(await evaluate('frame'), startFrame);

await evaluate('document.getElementById("next").click()');
assert.match(await evaluate('document.getElementById("frame").textContent'),/^2 \/ 631/);
await evaluate('document.getElementById("timeline").value="100";document.getElementById("timeline").dispatchEvent(new Event("input"))');
assert.match(await evaluate('document.getElementById("frame").textContent'),/^101 \/ 631/);
const before=await evaluate('document.getElementById("distance").textContent');
await evaluate('document.getElementById("marker-b").value="0";document.getElementById("marker-b").dispatchEvent(new Event("change"))');
assert.equal(await evaluate('document.getElementById("distance").textContent'),"0.0000 m");
await evaluate('document.getElementById("marker-b").value="1";document.getElementById("marker-b").dispatchEvent(new Event("change"))');
assert.equal(await evaluate('document.getElementById("distance").textContent'),before);
await evaluate('document.getElementById("play").click()');
await until('document.getElementById("timeline").value>105');
await evaluate('document.getElementById("play").click();document.getElementById("side").click();document.getElementById("reset").click()');
await evaluate('window.saved=[];URL.createObjectURL=(blob)=>{window.saved.push(blob);return "blob:test"};HTMLAnchorElement.prototype.click=function(){};document.getElementById("export").click()');
const csv=await evaluate('window.saved[0].text()');assert.equal(csv.trim().split("\n").length,632);
await evaluate('document.getElementById("snapshot").click()');
const html=await evaluate('window.saved[1].text()');
assert(html.includes('data-theme="dark"'));
assert(html.includes('data-skeleton-color="auto"'));

// Test snapshot exported in light mode
await evaluate('document.getElementById("btn-toggle-theme").click()');
await evaluate('document.getElementById("snapshot").click()');
const htmlLight = await evaluate('window.saved[2].text()');
assert(htmlLight.includes('data-theme="light"'));
await evaluate('document.getElementById("btn-toggle-theme").click()');

await writeFile(outputDir+"/browser_snapshot.html",html);
await send("Page.navigate",{url:"file://"+outputDir+"/browser_snapshot.html"});
await until('document.getElementById("frame")?.textContent.includes("631")');
const screenshot=await send("Page.captureScreenshot",{format:"png"});
await writeFile(outputDir+"/viewer.png",Buffer.from(screenshot.data,"base64"));
if(process.argv[3]){
 await send("Page.navigate",{url:process.argv[3]});
 await until('document.getElementById("file") && !document.getElementById("open-panel").hidden');
 const welcomeBtnWorks = await evaluate('let clicked = false; const f = document.getElementById("file"); const oldClick = f.click; f.click = () => { clicked = true; }; document.getElementById("btn-welcome-select").click(); f.click = oldClick; clicked');
 assert.equal(welcomeBtnWorks, true);
 const doc=await send("DOM.getDocument");const node=await send("DOM.querySelector",{nodeId:doc.root.nodeId,selector:"#file"});
 for(const filename of ["pilot0102_squat03.c3d","rec3d_20260826_121305_m.c3d","rec3d_20260826_121305.csv","rec3d_20260826_121305.3d"]){
  await evaluate('document.getElementById("status").textContent=""');
  await send("DOM.setFileInputFiles",{nodeId:node.nodeId,files:[root+"/data/"+filename]});
  await until('document.getElementById("status")?.textContent.includes("File loaded") || document.getElementById("status")?.textContent.includes("Arquivo carregado")');
  assert.equal(await evaluate('document.getElementById("plot1-mode").value'), "active-xyz");
  assert.equal(await evaluate('document.getElementById("plot2-mode").value'), "active-z");
  if (filename === "pilot0102_squat03.c3d") {
    assert.ok(await evaluate('trial.force_plates.length > 0'));
    assert.ok(await evaluate('document.querySelector("#plot1-mode option[value=fp-all-fz]")'));
    await evaluate('document.getElementById("plot1-mode").value = "fp-all-fz"; saveSessionState(); load(trial)');
    assert.equal(await evaluate('document.getElementById("plot1-mode").value'), "fp-all-fz");
  }
  const frameText = await evaluate('document.getElementById("frame").textContent');
  assert(frameText.includes("6772") || frameText.includes("631"), "unexpected frame: " + frameText);
 }
 await evaluate('document.getElementById("action-help-shortcuts").click()');
 assert.equal(await evaluate('document.getElementById("modal-shortcuts").classList.contains("open")'), true);
 await evaluate('document.getElementById("btn-close-shortcuts").click()');
 assert.equal(await evaluate('document.getElementById("modal-shortcuts").classList.contains("open")'), false);
 await evaluate('document.getElementById("rate").value = "120"; document.getElementById("btn-apply-rate").click();');
 assert.equal(await evaluate('trial.rate_hz'), 120);
 assert.match(await evaluate('document.getElementById("meta").textContent'), /120 Hz/);
 await evaluate('document.getElementById("skeleton-template-select").value = "sam3dinov3_mhr70"; document.getElementById("btn-load-skeleton").click();');
 assert.equal(await evaluate('skeletonPairs.length'), 88);
  await evaluate('document.getElementById("action-kinematics-modal").click();');
  assert.equal(await evaluate('document.getElementById("modal-kinematics").hidden'), false);
  await evaluate('document.getElementById("btn-compute-kinematics").click();');
  await until('document.getElementById("kinematics-status-badge").textContent.includes("Live")');
  assert.equal(await evaluate('analysisResults.orientations[0].quaternion_convention'), "scalar-first wxyz");
  assert.deepEqual(await evaluate('Object.keys(analysisResults.orientations[0].euler).sort()'), ["xyz","xzy","yxz","yzx","zxy","zyx"]);
  await evaluate('document.getElementById("btn-close-kinematics").click();');
  await evaluate('document.getElementById("action-kinematics-plot-euler").click()');
  assert.equal(await evaluate('document.getElementById("plot1-mode").value'), "kinematics-euler");
 await evaluate('document.getElementById("btn-create-com").click();');
 assert.equal(await evaluate('trial.labels.at(-1)'), "CenterOfMass_deLeva_male");
 assert.equal(await evaluate('trial.xyz[0].length'), 71);
 assert.equal(await evaluate('rawLoadedXYZ[0].length'), 71);
 const editedC3DBytes = await evaluate(`fetch("/api/export/c3d", {
   method: "POST",
   headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
   body: JSON.stringify(trial)
 }).then(async r => r.ok ? (await r.arrayBuffer()).byteLength : 0)`);
 assert.ok(editedC3DBytes > 512);
  const projectRoundTrip = await evaluate(`(async () => {
    document.getElementById("plot1-mode").value = "active-speed";
    document.getElementById("plot2-mode").value = "distance";
    setSidebarVisible(false);
    setSkeletonColor("#f97316", "Orange");
    setSelectedMarkers([1, 4, 7]);
    const viewerState = collectViewerState();
    viewerState.raw_loaded_xyz = rawLoadedXYZ;
    viewerState.raw_force_plates = rawForcePlates;
    const saved = await fetch("/api/export/vaila", {
      method: "POST",
      headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
      body: JSON.stringify({trial, viewer_state: viewerState, analyses: collectAnalysisResults()})
    });
    if (!saved.ok) return {ok:false, stage:"save"};
    const archive = await saved.blob();
    const reopened = await fetch("/api/trial?name=browser-roundtrip.vaila", {
      method: "POST",
      headers: {"Authorization": "Bearer " + token},
      body: archive
    });
    if (!reopened.ok) return {ok:false, stage:"open"};
    const data = await reopened.json();
    loadVailaProject(data.project);
    return {
      ok: true,
      rate: trial.rate_hz,
      markers: trial.labels.length,
      orientations: analysisResults.orientations.length,
      filtered: Boolean(activeFilterConfig),
      plot1: document.getElementById("plot1-mode").value,
      plot2: document.getElementById("plot2-mode").value,
      sidebarHidden: document.getElementById("sidebar").hidden,
      skeletonColor,
      selectedMarkers: Array.from(selectedMarkerIndices).sort((a, b) => a - b)
    };
  })()`);
  assert.deepEqual(projectRoundTrip, {
    ok: true,
    rate: 120,
    markers: 71,
    orientations: 1,
    filtered: false,
    plot1: "active-speed",
    plot2: "distance",
    sidebarHidden: true,
    skeletonColor: "#f97316",
    selectedMarkers: [1, 4, 7]
  });
 await evaluate('document.getElementById("btn-clear-skeleton").click()');
 assert.equal(await evaluate('skeletonPairs.length'), 0);

  // Test Right-Click Context Menu on 3D Canvas
  // 1. Right-click with 2 selected markers
  await evaluate('setSelectedMarkers([1, 2]); canvas.dispatchEvent(new MouseEvent("contextmenu", {clientX: 400, clientY: 300, bubbles: true, cancelable: true}))');
  assert.equal(await evaluate('document.getElementById("canvas-context-menu").hidden'), false);
  assert.equal(await evaluate('document.getElementById("ctx-action-create-segment").disabled'), false);
  assert.equal(await evaluate('document.getElementById("ctx-action-create-lcs").disabled'), true);
  assert.equal(await evaluate('document.getElementById("ctx-action-compute-kinematics").disabled'), true);

  // 2. Create named segment via context menu action
  await evaluate('createSegmentFromSelected("Thigh_Right")');
  assert.equal(await evaluate('skeletonPairs.length'), 1);
  assert.equal(await evaluate('customSegments.some(s => s[2] === "Thigh_Right")'), true);

  // 3. Right-click with 3 selected markers
  await evaluate('setSelectedMarkers([1, 2, 3]); canvas.dispatchEvent(new MouseEvent("contextmenu", {clientX: 450, clientY: 320, bubbles: true, cancelable: true}))');
  assert.equal(await evaluate('document.getElementById("canvas-context-menu").hidden'), false);
  assert.equal(await evaluate('document.getElementById("ctx-action-create-lcs").disabled'), false);
  assert.equal(await evaluate('document.getElementById("ctx-action-create-lcs-s2").disabled'), false);
  assert.equal(await evaluate('document.getElementById("ctx-action-compute-kinematics").disabled'), false);

  // 4. Compute Kinematics via context menu action
  await evaluate('computeKinematicsFromSelected("Pelvis_LCS", "s1")');
  assert.equal(await evaluate('document.getElementById("modal-kinematics").hidden'), false);
  assert.equal(await evaluate('document.getElementById("s1-name").value'), "Pelvis_LCS");
  assert.ok(await evaluate('kinematicsConfig.computed && Array.isArray(kinematicsData.MR)'));
  assert.ok(await evaluate('document.getElementById("kinematics-status-badge").textContent.includes("Live")'));
  assert.equal(await evaluate('kinematicsConfig.showTriads'), true);
  await evaluate('document.getElementById("btn-close-kinematics").click()');

  // 5. Test right-click release does not deselect or clear markers
  await evaluate('canvas.dispatchEvent(new PointerEvent("pointerdown", {clientX: 400, clientY: 300, button: 2, bubbles: true}))');
  await evaluate('canvas.dispatchEvent(new PointerEvent("pointerup", {clientX: 400, clientY: 300, button: 2, bubbles: true}))');
  assert.equal(await evaluate('selectedMarkerIndices.size'), 3);

  // 6. Test Esc key hides context menu
  await evaluate('document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}))');
  assert.equal(await evaluate('document.getElementById("canvas-context-menu").hidden'), true);
}
assert.deepEqual(errors,[]);
console.log("Browser passed: playback, FPS edit, filtering, exports, de Leva CoM, detailed skeleton, local uploads, and no JS exceptions.");
ws.close();
