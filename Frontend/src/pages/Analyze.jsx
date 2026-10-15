import { useRef, useState } from 'react';
import { postAnalyze } from '../services/api.js';
import { formatBytes } from '../utils/format.js';
import ResultCard from '../components/ResultCard.jsx';

const MAX_MB = 200;
const MAX_BYTES = MAX_MB * 1024 * 1024;

export default function Analyze() {
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | uploading | analyzing | done
  const [progress, setProgress] = useState(0);
  const [analysis, setAnalysis] = useState(null);
  const [historyNotice, setHistoryNotice] = useState('');
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function pick(f) {
    setError('');
    setAnalysis(null);
    setHistoryNotice('');
    if (!f) return;
    const ext = f.name.toLowerCase();
    if (!ext.endsWith('.pcap') && !ext.endsWith('.pcapng')) {
      setError('Please select a PCAP or PCAPNG file.');
      return;
    }
    if (f.size === 0) {
      setError('The selected file is empty.');
      return;
    }
    if (f.size > MAX_BYTES) {
      setError(`This file is larger than the allowed upload limit (${MAX_MB} MB).`);
      return;
    }
    setFile(f);
  }

  async function onAnalyze() {
    if (!file || phase === 'uploading' || phase === 'analyzing') return;
    setError('');
    setPhase('uploading');
    setProgress(0);
    try {
      const res = await postAnalyze(file, (p) => {
        setProgress(p);
        if (p >= 100) setPhase('analyzing');
      });
      setPhase('analyzing');
      setAnalysis(res.analysis);
      if (res.historyNotice) setHistoryNotice(res.historyNotice);
      setPhase('done');
    } catch (e) {
      setPhase('idle');
      setError(e.message);
    }
  }

  function reset() {
    setFile(null);
    setError('');
    setAnalysis(null);
    setHistoryNotice('');
    setPhase('idle');
    setProgress(0);
    if (inputRef.current) inputRef.current.value = '';
  }

  const busy = phase === 'uploading' || phase === 'analyzing';

  return (
    <div className="container">
      <div className="card">
        <h1>Analyze Traffic</h1>
        <p className="muted">Upload one network capture (.pcap or .pcapng, up to {MAX_MB} MB).</p>

        <div
          className={`dropzone${dragging ? ' dragging' : ''}`}
          onClick={() => inputRef.current && inputRef.current.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files && e.dataTransfer.files[0]);
          }}
        >
          <p>
            <strong>Drag &amp; drop your capture here</strong>
          </p>
          <p className="muted">or</p>
          <button type="button" className="btn" onClick={(e) => {
            e.stopPropagation();
            inputRef.current && inputRef.current.click();
          }}>
            Choose PCAP File
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pcap,.pcapng"
            style={{ display: 'none' }}
            onChange={(e) => pick(e.target.files && e.target.files[0])}
          />
        </div>

        {file && (
          <div className="card" style={{ margin: '12px 0' }}>
            <p>
              <strong>{file.name}</strong> — {formatBytes(file.size)}
            </p>
            <button type="button" className="btn secondary" onClick={reset} disabled={busy}>
              Remove file
            </button>
          </div>
        )}

        {error && <div className="alert error">{error}</div>}

        <button type="button" className="btn" onClick={onAnalyze} disabled={!file || busy}>
          {busy ? 'Analyzing…' : 'Analyze Traffic'}
        </button>

        {phase === 'uploading' && (
          <p>
            <span className="spinner" /> Uploading file… {progress}%
          </p>
        )}
        {phase === 'analyzing' && !analysis && (
          <p>
            <span className="spinner" /> Analyzing… reading network packets, extracting features, and running the model.
          </p>
        )}
      </div>

      {historyNotice && <div className="alert info">{historyNotice}</div>}

      {analysis && (
        <div>
          <ResultCard analysis={analysis} />
          <div className="card">
            <button type="button" className="btn secondary" onClick={reset}>
              Start New Analysis
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
