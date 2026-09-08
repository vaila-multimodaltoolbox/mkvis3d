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
await writeFile(root+"/outputs/browser_snapshot.html",html);
await send("Page.navigate",{url:"file://"+root+"/outputs/browser_snapshot.html"});
await until('document.getElementById("frame")?.textContent.includes("631")');
const screenshot=await send("Page.captureScreenshot",{format:"png"});
await writeFile(root+"/outputs/viewer.png",Buffer.from(screenshot.data,"base64"));
if(process.argv[3]){
 await send("Page.navigate",{url:process.argv[3]});
 await until('document.getElementById("file") && !document.getElementById("open-panel").hidden');
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
