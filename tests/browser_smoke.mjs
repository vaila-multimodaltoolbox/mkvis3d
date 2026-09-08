import {writeFile} from "node:fs/promises";
import assert from "node:assert/strict";
const root=process.argv[2] || process.cwd();
const cdpPort = process.env.CDP_PORT || "9237";
const targets=await (await fetch("http://127.0.0.1:"+cdpPort+"/json/list")).json();
const ws=new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
await new Promise(resolve=>ws.addEventListener("open",resolve,{once:true}));
let next=0;const pending=new Map(),errors=[];
ws.addEventListener("message",e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);if(r.error)p.reject(new Error(JSON.stringify(r.error)));else p.resolve(r.result);}else if(r.method==="Runtime.exceptionThrown")errors.push(r.params.exceptionDetails);});
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw new Error("Timeout: "+expression);}
await send("Runtime.enable");await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride",{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
await send("Page.navigate",{url:"file://"+root+"/outputs/rec3d_viewer.html"});
await until('document.getElementById("frame")?.textContent.includes("631")');
assert.match(await evaluate('document.getElementById("meta").textContent'),/70 markers|70 marcadores/);
assert.equal(await evaluate('document.getElementById("open-panel").hidden'),true);

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
await writeFile(root + "/outputs/viewer_light.png", Buffer.from(lightShot.data, "base64"));

// Switch to Dark Mode via View menu
await evaluate('document.getElementById("action-theme-dark").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");

// Switch to Light Mode via View menu
await evaluate('document.getElementById("action-theme-light").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "light");

// Switch to Dark Mode via Options menu
await evaluate('document.getElementById("action-opt-theme-dark").click()');
assert.equal(await evaluate('document.documentElement.getAttribute("data-theme")'), "dark");

// Switch to Light Mode via Options menu
await evaluate('document.getElementById("action-opt-theme-light").click()');
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

// Test Vertical Splitter between 3D Viewport and Charts
assert.ok(await evaluate('Boolean(document.getElementById("vertical-splitter"))'));
await evaluate('document.getElementById("windows-container").style.setProperty("--plot-height", "220px"); resize()');
assert.equal(await evaluate('getComputedStyle(document.getElementById("windows-container")).getPropertyValue("--plot-height").trim()'), "220px");

// Capture screenshot demonstrating custom orange markers + resized vertical splitter
await evaluate('setMarkerColor("#f97316", "Orange"); setMarkerSize(5.0);');
const markerShot = await send("Page.captureScreenshot", { format: "png" });
await writeFile(root + "/outputs/viewer_custom_markers.png", Buffer.from(markerShot.data, "base64"));

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

// Test snapshot exported in light mode
await evaluate('document.getElementById("btn-toggle-theme").click()');
await evaluate('document.getElementById("snapshot").click()');
const htmlLight = await evaluate('window.saved[2].text()');
assert(htmlLight.includes('data-theme="light"'));
await evaluate('document.getElementById("btn-toggle-theme").click()');

await writeFile(root+"/outputs/browser_snapshot.html",html);
await send("Page.navigate",{url:"file://"+root+"/outputs/browser_snapshot.html"});
await until('document.getElementById("frame")?.textContent.includes("631")');
const screenshot=await send("Page.captureScreenshot",{format:"png"});
await writeFile(root+"/outputs/viewer.png",Buffer.from(screenshot.data,"base64"));
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
  const frameText = await evaluate('document.getElementById("frame").textContent');
  assert(frameText.includes("6772") || frameText.includes("631"), "unexpected frame: " + frameText);
 }
 await evaluate('document.getElementById("action-view-shortcuts").click()');
 assert.equal(await evaluate('document.getElementById("modal-shortcuts").classList.contains("open")'), true);
 await evaluate('document.getElementById("btn-close-shortcuts").click()');
 assert.equal(await evaluate('document.getElementById("modal-shortcuts").classList.contains("open")'), false);
 await evaluate('document.getElementById("skeleton-template-select").value = "sam3dinov3_mhr70"; document.getElementById("btn-load-skeleton").click();');
 assert.equal(await evaluate('skeletonPairs.length'), 30);
 await evaluate('document.getElementById("btn-clear-skeleton").click()');
 assert.equal(await evaluate('skeletonPairs.length'), 0);
}
assert.deepEqual(errors,[]);
console.log("Browser passed: golden trial, stepping, seek, playback, selection, distance CSV, saved HTML reload, local C3D/CSV/.3d upload, modal close, skeleton template manual load, no JS exceptions.");
ws.close();
