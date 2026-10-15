export function formatBytes(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return 'Unavailable';
  const n = Number(bytes);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatSeconds(s) {
  if (s == null || Number.isNaN(Number(s))) return 'Unavailable';
  return `${Number(s).toFixed(1)} s`;
}

export function formatDateTime(iso) {
  if (!iso) return 'Unavailable';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

export function valueOrUnavailable(v) {
  return v == null ? 'Unavailable' : v;
}
