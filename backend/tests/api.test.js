const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// --- test env: small upload limit so the 413 path is exercisable ---
process.env.PORT = '5001';
process.env.ML_SERVICE_URL = 'http://127.0.0.1:8001';
process.env.FRONTEND_ORIGIN = 'http://localhost:5173';
process.env.MAX_FILE_MB = '1';
process.env.ML_TIMEOUT_MS = '120000';
process.env.MAX_CONCURRENT_ANALYSES = '4';
delete process.env.MONGODB_URI;

const BACKEND_ROOT = path.join(__dirname, '..');
const PROJECT_ROOT = path.join(BACKEND_ROOT, '..');
const DEMO_NONVPN = path.join(PROJECT_ROOT, 'data', 'raw', 'NonVPN-PCAPs-01', 'facebookchat1.pcapng');
const DEMO_VPN = path.join(PROJECT_ROOT, 'data', 'raw', 'VPN-PCAPS-01', 'vpn_aim_chat1a.pcap');
const BASE = 'http://127.0.0.1:5001';

let uvicorn = null;
let server = null;

function waitFor(url, timeoutMs = 60000) {
  const t0 = Date.now();
  return (async () => {
    for (;;) {
      try {
        const r = await fetch(url);
        if (r.ok) return;
      } catch (e) { /* retry */ }
      if (Date.now() - t0 > timeoutMs) throw new Error(`timeout waiting for ${url}`);
      await new Promise((r) => setTimeout(r, 1000));
    }
  })();
}

before(async () => {
  const py = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe');
  uvicorn = spawn(py, ['-m', 'uvicorn', 'ml_service.app:app', '--port', '8001'], {
    cwd: PROJECT_ROOT,
    stdio: 'ignore',
  });
  await waitFor('http://127.0.0.1:8001/health');
  const { app, start } = require('../src/server.js');
  await start();
  await waitFor(`${BASE}/api/health`);
});

after(async () => {
  const { close } = require('../src/server.js');
  if (uvicorn) uvicorn.kill();
  await close().catch(() => {});
  await new Promise((r) => setTimeout(r, 500));
});

async function postFile(name, buffer, contentType = 'application/octet-stream') {
  const form = new FormData();
  form.append('file', new Blob([buffer], { type: contentType }), name);
  return fetch(`${BASE}/api/analyze`, { method: 'POST', body: form });
}

function tmpUploadsEmpty() {
  const dir = path.join(BACKEND_ROOT, 'tmp', 'uploads');
  if (!fs.existsSync(dir)) return true;
  return fs.readdirSync(dir).length === 0;
}

let savedId = null;

test('health endpoint', async () => {
  const r = await fetch(`${BASE}/api/health`);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.status, 'ok');
  assert.equal(j.mlServiceReachable, true);
});

test('model-info endpoint returns real metadata', async () => {
  const r = await fetch(`${BASE}/api/model-info`);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.success, true);
  assert.match(j.model.model_version, /1\.0\.0/);
  assert.deepEqual(j.model.label_mapping, { nonvpn: 0, vpn: 1 });
  assert.ok(j.model.n_features === 24);
});

test('valid PCAPNG (non-VPN) upload -> real prediction', async () => {
  const buf = fs.readFileSync(DEMO_NONVPN);
  const r = await postFile('facebookchat1.pcapng', buf);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.success, true);
  assert.ok(['vpn', 'nonvpn'].includes(j.analysis.predictedLabel));
  assert.equal(typeof j.analysis.probabilities.nonvpn, 'number');
  assert.equal(typeof j.analysis.probabilities.vpn, 'number');
  // class-to-probability mapping: predicted label must hold the max probability
  const p = j.analysis.probabilities;
  const argmax = p.nonvpn >= p.vpn ? 'nonvpn' : 'vpn';
  assert.equal(j.analysis.predictedLabel, argmax);
  assert.ok(j.analysis.packetCount > 0 && j.analysis.featureSampleCount > 0);
  assert.ok(tmpUploadsEmpty(), 'temp upload was not cleaned up');
  savedId = j.analysis.id;
});

test('valid PCAP (VPN) upload -> real prediction', async () => {
  const buf = fs.readFileSync(DEMO_VPN);
  const r = await postFile('vpn_aim_chat1a.pcap', buf);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.analysis.predictedLabel, 'vpn');
  assert.ok(tmpUploadsEmpty(), 'temp upload was not cleaned up');
});

test('unsupported extension rejected with friendly message', async () => {
  const r = await postFile('notes.txt', Buffer.from('hello'));
  assert.equal(r.status, 400);
  const j = await r.json();
  assert.equal(j.success, false);
  assert.match(j.error, /PCAP/i);
  assert.ok(!JSON.stringify(j).includes('Traceback'));
});

test('empty file rejected', async () => {
  const r = await postFile('empty.pcap', Buffer.alloc(0));
  assert.equal(r.status, 400);
  const j = await r.json();
  assert.equal(j.success, false);
});

test('malformed capture handled without crash or traceback', async () => {
  const r = await postFile('bad.pcap', Buffer.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]));
  assert.ok([400, 422].includes(r.status));
  const j = await r.json();
  assert.equal(j.success, false);
  assert.ok(!JSON.stringify(j).includes('Traceback'));
  assert.ok(tmpUploadsEmpty(), 'temp upload was not cleaned up');
});

test('oversized file rejected (1 MB test limit)', async () => {
  const big = Buffer.alloc(2 * 1024 * 1024, 0);
  const r = await postFile('big.pcap', big);
  assert.equal(r.status, 413);
  const j = await r.json();
  assert.match(j.error, /larger than the allowed/i);
});

test('history + report download (non-persistent mode)', async () => {
  assert.ok(savedId, 'no saved analysis id from earlier test');
  const l = await fetch(`${BASE}/api/analysis`);
  const lj = await l.json();
  assert.equal(lj.success, true);
  assert.equal(lj.persistent, false);
  assert.ok(lj.items.length >= 2);
  const g = await fetch(`${BASE}/api/analysis/${savedId}`);
  assert.equal((await g.json()).analysis.id, savedId);
  const rep = await fetch(`${BASE}/api/analysis/${savedId}/report?format=json`);
  assert.equal(rep.status, 200);
  assert.match(rep.headers.get('content-disposition') || '', /attachment/);
  const rj = await rep.json();
  assert.equal(rj.analysisId, savedId);
  assert.ok(rj.disclaimer);
  const csv = await fetch(`${BASE}/api/analysis/${savedId}/report?format=csv`);
  assert.equal(csv.status, 200);
  assert.match(await csv.text(), /predictedClass/);
});

test('ML unavailable -> friendly 503 (killed last)', async () => {
  uvicorn.kill();
  await new Promise((r) => setTimeout(r, 2000));
  const h = await fetch(`${BASE}/api/health`);
  assert.equal((await h.json()).mlServiceReachable, false);
  const m = await fetch(`${BASE}/api/model-info`);
  assert.equal(m.status, 503);
  const buf = fs.readFileSync(DEMO_NONVPN);
  const r = await postFile('facebookchat1.pcapng', buf);
  assert.equal(r.status, 503);
  assert.match((await r.json()).error, /machine learning service is unavailable/i);
});
