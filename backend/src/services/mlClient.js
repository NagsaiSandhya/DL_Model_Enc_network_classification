const fs = require('fs');
const config = require('../config');

const FRIENDLY = {
  400: 'The selected capture could not be read.',
  413: 'This file is larger than the allowed upload limit.',
  422: 'No usable traffic features were found in this capture.',
};

/**
 * Forward a capture file to the Python ML service.
 * Uses native fetch/FormData (no shell, no user-controlled command strings).
 */
async function predictCapture(absPath, originalName) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.ML_TIMEOUT_MS);
  try {
    const buf = fs.readFileSync(absPath);
    const form = new FormData();
    form.append('file', new Blob([buf], { type: 'application/octet-stream' }), originalName);
    let res;
    try {
      res = await fetch(`${config.ML_SERVICE_URL}/predict`, {
        method: 'POST',
        body: form,
        signal: controller.signal,
      });
    } catch (err) {
      if (err && err.name === 'AbortError') {
        const e = new Error('The analysis took too long. Please try a smaller capture.');
        e.status = 504;
        throw e;
      }
      const e = new Error('The machine learning service is unavailable. Please try again later.');
      e.status = 503;
      throw e;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      const msg =
        (data && data.detail) ||
        FRIENDLY[res.status] ||
        'The analysis failed. Please try again with a different capture.';
      const e = new Error(msg);
      e.status = res.status >= 400 && res.status < 600 ? res.status : 500;
      throw e;
    }
    return data.analysis;
  } finally {
    clearTimeout(timer);
  }
}

async function fetchModelInfo() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(`${config.ML_SERVICE_URL}/model-info`, { signal: controller.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function checkMlReachable() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(`${config.ML_SERVICE_URL}/health`, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch (err) {
    return false;
  }
}

module.exports = { predictCapture, fetchModelInfo, checkMlReachable };
