const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000').replace(/\/$/, '');

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) {
    throw new Error((data && data.error) || `Request failed (${res.status}). Please try again.`);
  }
  return data;
}

export function getHealth() {
  return fetch(`${API_BASE}/api/health`).then(handle);
}

export function getModelInfo() {
  return fetch(`${API_BASE}/api/model-info`).then(handle);
}

export function getHistory() {
  return fetch(`${API_BASE}/api/analysis`).then(handle);
}

export function getAnalysis(id) {
  return fetch(`${API_BASE}/api/analysis/${encodeURIComponent(id)}`).then(handle);
}

export function reportUrl(id, format = 'json') {
  return `${API_BASE}/api/analysis/${encodeURIComponent(id)}/report?format=${format}`;
}

/**
 * Upload with REAL upload progress (XMLHttpRequest). After 100% uploaded,
 * the promise stays pending while the server analyzes (indeterminate state).
 */
export function postAnalyze(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/analyze`);
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      const data = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300 && data.success) resolve(data);
      else reject(new Error((data && data.error) || `Analysis failed (${xhr.status}). Please try again.`));
    };
    xhr.onerror = () => reject(new Error('Could not reach the server. Please check it is running and try again.'));
    xhr.ontimeout = () => reject(new Error('The analysis took too long. Please try a smaller capture.'));
    const form = new FormData();
    form.append('file', file, file.name);
    xhr.send(form);
  });
}
