import fs from 'node:fs';
import { resolve } from 'node:path';

const cdpPort = process.env.CDP_PORT || "9280";
const root = resolve(process.cwd());

async function main() {
  const targets = await (await fetch(`http://127.0.0.1:${cdpPort}/json/list`)).json();
  const pageTarget = targets.find(t => t.type === 'page');
  if (!pageTarget) throw new Error('No page target found');

  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));

  let id = 1;
  const pending = new Map();
  ws.addEventListener('message', e => {
    const msg = JSON.parse(e.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    }
  });

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const msgId = id++;
    pending.set(msgId, { resolve, reject });
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });

  const evaluate = async expr => {
    const res = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (res.exceptionDetails) throw new Error(JSON.stringify(res.exceptionDetails));
    return res.result.value;
  };

  await send('Emulation.setDeviceMetricsOverride', {
    width: 1366,
    height: 850,
    deviceScaleFactor: 1,
    mobile: false
  });

  console.log('Navigating to generated HTML viewer...');
  await send('Page.navigate', { url: `file://${root}/outputs/rec3d_viewer.html` });
  await new Promise(r => setTimeout(r, 1500));

  // 1. Verify Sidebar Trajectory Buttons
  console.log('--- Checking Sidebar Point Selection Action Bar ---');
  const btnExportExists = await evaluate('Boolean(document.getElementById("btn-sidebar-export-csv"))');
  const btnBlankExists = await evaluate('Boolean(document.getElementById("btn-sidebar-blank-frame"))');
  const btnOpenTools = await evaluate('Boolean(document.getElementById("btn-sidebar-open-trajectory"))');
  console.log('Sidebar buttons present:', { btnExportExists, btnBlankExists, btnOpenTools });
  if (!btnExportExists || !btnBlankExists || !btnOpenTools) throw new Error('Sidebar buttons missing');

  // Test blanking current frame via sidebar button
  const p1_before_frame0 = await evaluate('window.trial.xyz[0][0]');
  console.log('p1 frame 0 before blanking:', p1_before_frame0);
  await evaluate('document.getElementById("btn-sidebar-blank-frame").click()');
  const p1_after_frame0 = await evaluate('window.trial.xyz[0][0]');
  console.log('p1 frame 0 after blanking:', p1_after_frame0);
  if (p1_after_frame0 !== null && !isNaN(p1_after_frame0[0])) {
    throw new Error('p1 frame 0 was not blanked to NaN/null');
  }

  // 2. Open Kinematics Modal Tab 1 (Points & Cleaning)
  console.log('--- Opening Kinematics Modal Tab 1 ---');
  await evaluate('document.getElementById("btn-sidebar-open-trajectory").click()');
  await new Promise(r => setTimeout(r, 400));

  const modalOpen = await evaluate('!document.getElementById("modal-kinematics").hidden');
  console.log('Kinematics modal opened:', modalOpen);
  if (!modalOpen) throw new Error('Kinematics modal failed to open');

  // 3. Test Frame Sequence Blanking & Restore
  console.log('--- Testing Sequence Blanking & Restore in Modal ---');
  // Select Sequence Range: frames 10 to 20
  await evaluate('document.getElementById("radio-clean-range").click()');
  await evaluate('document.getElementById("clean-range-start").value = "10"');
  await evaluate('document.getElementById("clean-range-end").value = "20"');
  await evaluate('document.getElementById("btn-clean-blank-action").click()');
  await new Promise(r => setTimeout(r, 300));

  // Verify frames 10..20 are blanked
  const p1_frame10 = await evaluate('window.trial.xyz[10][0]');
  const p1_frame20 = await evaluate('window.trial.xyz[20][0]');
  const p1_frame25 = await evaluate('window.trial.xyz[25][0]');
  console.log('p1 frames after range blank: f10 =', p1_frame10, 'f20 =', p1_frame20, 'f25 =', p1_frame25);
  if ((p1_frame10 !== null && !isNaN(p1_frame10[0])) || (p1_frame20 !== null && !isNaN(p1_frame20[0]))) {
    throw new Error('Range 10..20 was not blanked properly');
  }
  if (p1_frame25 === null || isNaN(p1_frame25[0])) {
    throw new Error('Frame 25 should still be valid');
  }

  // Restore marker
  await evaluate('document.getElementById("btn-clean-restore-marker").click()');
  await new Promise(r => setTimeout(r, 300));
  const p1_restored10 = await evaluate('window.trial.xyz[10][0]');
  console.log('p1 frame 10 restored:', p1_restored10);
  if (p1_restored10 === null || isNaN(p1_restored10[0])) {
    throw new Error('Marker p1 was not restored properly');
  }

  // 4. Test CSV Trajectory Mode (Create New Point from CSV)
  console.log('--- Testing CSV Trajectory Mode (Create New Point) ---');
  await evaluate('document.getElementById("btn-vp-mode-csv").click()');
  const csvContainerVis = await evaluate('document.getElementById("vp-container-csv").style.display !== "none"');
  console.log('CSV Trajectory container visible:', csvContainerVis);
  if (!csvContainerVis) throw new Error('CSV container not visible');

  // Inject a synthetic CSV text into parser and populate
  const nFrames = await evaluate('window.trial.xyz.length');
  const mockCsv = `frame,time_s,x,y,z\n` + Array.from({length: nFrames}, (_, i) => `${i},${(i*0.01).toFixed(3)},${(1.234 + i*0.001).toFixed(4)},0.5000,1.8000`).join('\n');
  
  await evaluate(`(function() {
    parsedCsvTrajectory = parseTrajectoryCSV(${JSON.stringify(mockCsv)}, window.trial.xyz.length);
    parsedCsvFilename = "mock_trajectory.csv";
    document.getElementById("vp-csv-status-badge").textContent = "✓ Loaded mock_trajectory.csv: " + parsedCsvTrajectory.length + " frames.";
    document.getElementById("vp-name").value = "P_CSV_TEST";
  })()`);

  // Click Create Point
  await evaluate('document.getElementById("btn-add-virtual-point").click()');
  await new Promise(r => setTimeout(r, 400));

  // Verify created point
  const tableContent = await evaluate('document.getElementById("vp-table-body").textContent');
  console.log('Table content after CSV add:', tableContent);
  if (!tableContent.includes('P_CSV_TEST')) throw new Error('P_CSV_TEST not in table');
  if (!tableContent.includes('CSV [mock_trajectory.csv]')) throw new Error('CSV indicator not in table');

  const labelExists = await evaluate('window.trial.labels.includes("P_CSV_TEST")');
  console.log('P_CSV_TEST in window.trial.labels:', labelExists);
  if (!labelExists) throw new Error('P_CSV_TEST missing in trial.labels');

  // 5. Test CSV Replace Existing Marker
  console.log('--- Testing CSV Trajectory Replace Option ---');
  await evaluate('document.getElementById("vp-csv-dest-replace").click()');
  const replaceRowVis = await evaluate('document.getElementById("vp-csv-replace-row").style.display !== "none"');
  console.log('Replace target selector visible:', replaceRowVis);
  if (!replaceRowVis) throw new Error('Replace row not visible');

  // Set replace marker to p2 (idx 1) with constant [2.5, 3.5, 4.5]
  const mockReplaceCsv = Array.from({length: nFrames}, () => `2.5000, 3.5000, 4.5000`).join('\n');
  await evaluate(`(function() {
    parsedCsvTrajectory = parseTrajectoryCSV(${JSON.stringify(mockReplaceCsv)}, window.trial.xyz.length);
    parsedCsvFilename = "replaced_p2.csv";
    document.getElementById("vp-csv-replace-marker").value = "1";
  })()`);

  await evaluate('document.getElementById("btn-add-virtual-point").click()');
  await new Promise(r => setTimeout(r, 400));

  const p2_new_frame0 = await evaluate('window.trial.xyz[0][1]');
  console.log('p2 frame 0 after replace:', p2_new_frame0);
  if (Math.abs(p2_new_frame0[0] - 2.5) > 1e-3 || Math.abs(p2_new_frame0[1] - 3.5) > 1e-3) {
    throw new Error('p2 was not replaced with CSV trajectory: ' + JSON.stringify(p2_new_frame0));
  }

  // 6. Capture Screenshots
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(`${root}/outputs/screenshot_point_csv_cleaning.png`, Buffer.from(shot.data, 'base64'));
  console.log('Saved screenshot: outputs/screenshot_point_csv_cleaning.png');

  console.log('=== ALL POINT CSV & CLEANING E2E TESTS PASSED SUCCESSFULLY! ===');
  ws.close();
}

main().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
