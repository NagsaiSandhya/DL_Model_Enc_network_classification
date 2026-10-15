/* Full-stack E2E: ML service + backend + served frontend, real captures.
   Run from demo1/:  node e2e_check.js  (kills children on exit) */
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = __dirname;
const PY = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
const children = [];

function start(cmd, args, cwd, env = {}) {
  const p = spawn(cmd, args, { cwd, env: { ...process.env, ...env }, stdio: 'ignore' });
  children.push(p);
  return p;
}

async function waitFor(url, timeoutMs = 90000) {
  const t0 = Date.now();
  for (;;) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
    } catch (e) { /* retry */ }
    if (Date.now() - t0 > timeoutMs) throw new Error('timeout: ' + url);
    await new Promise((r) => setTimeout(r, 1000));
  }
}

(async () => {
  start(PY, ['-m', 'uvicorn', 'ml_service.app:app', '--port', '8000'], ROOT);
  await waitFor('http://127.0.0.1:8000/health');
  console.log('ML service up');

  start('node', ['src/server.js'], path.join(ROOT, 'backend'), { PORT: '5000' });
  await waitFor('http://127.0.0.1:5000/api/health');
  console.log('Backend up');

  start('node', [path.join(ROOT, 'Frontend', 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', '5173', '--strictPort', '--host', '127.0.0.1'], path.join(ROOT, 'Frontend'));
  await waitFor('http://127.0.0.1:5173/');
  console.log('Frontend up');

  // 1. frontend serves app shell + bundle
  const html = await (await fetch('http://127.0.0.1:5173/')).text();
  if (!html.includes('id="root"')) throw new Error('frontend shell missing');
  console.log('PASS frontend shell served');

  // 2. backend health shows ML reachable
  const health = await (await fetch('http://127.0.0.1:5000/api/health')).json();
  if (health.mlServiceReachable !== true) throw new Error('ML not reachable from backend');
  console.log('PASS backend health, ML reachable');

  // 3. model-info real
  const mi = await (await fetch('http://127.0.0.1:5000/api/model-info')).json();
  if (!mi.success || mi.model.n_features !== 24) throw new Error('model-info bad');
  console.log('PASS model-info', mi.model.model_version);

  // 4. real VPN + non-VPN uploads through the whole stack
  async function analyze(absPath, name) {
    const buf = fs.readFileSync(absPath);
    const form = new FormData();
    form.append('file', new Blob([buf]), name);
    const r = await fetch('http://127.0.0.1:5000/api/analyze', { method: 'POST', body: form });
    const j = await r.json();
    if (!j.success) throw new Error('analyze failed: ' + JSON.stringify(j));
    return j.analysis;
  }
  const nonvpn = await analyze(path.join(ROOT, 'data', 'raw', 'NonVPN-PCAPs-01', 'facebookchat1.pcapng'), 'facebookchat1.pcapng');
  console.log('PASS nonVPN upload ->', nonvpn.predictedLabel, JSON.stringify(nonvpn.probabilities));
  const vpn = await analyze(path.join(ROOT, 'data', 'raw', 'VPN-PCAPS-01', 'vpn_aim_chat1a.pcap'), 'vpn_aim_chat1a.pcap');
  console.log('PASS VPN upload ->', vpn.predictedLabel, JSON.stringify(vpn.probabilities));
  if (nonvpn.predictedLabel !== 'nonvpn') throw new Error('nonVPN mismatch');
  if (vpn.predictedLabel !== 'vpn') throw new Error('VPN mismatch');
  if (!nonvpn.charts || !nonvpn.charts.packet_length_hist) throw new Error('charts missing');

  // 5. report download reflects actual result
  const rep = await (await fetch(`http://127.0.0.1:5000/api/analysis/${nonvpn.id}/report?format=json`)).json();
  if (rep.predictedClass !== nonvpn.predictedLabel) throw new Error('report mismatch');
  console.log('PASS report download');

  console.log('E2E ALL PASSED');
  process.exitCode = 0;
})().catch((e) => {
  console.error('E2E FAILED:', e.message);
  process.exitCode = 1;
}).finally(() => {
  setTimeout(() => {}, 300);
  for (const c of children) try { c.kill(); } catch (e) { /* ignore */ }
  setTimeout(() => process.exit(process.exitCode || 0), 1500);
});
