import { useState } from 'react';
import { getAnalysis, reportUrl } from '../services/api.js';
import { useHistory } from '../hooks/useApi.js';
import { formatDateTime } from '../utils/format.js';
import ResultCard from '../components/ResultCard.jsx';

export default function History() {
  const { data, error, loading } = useHistory();
  const [open, setOpen] = useState(null);
  const [openError, setOpenError] = useState('');

  async function view(id) {
    setOpenError('');
    try {
      const res = await getAnalysis(id);
      setOpen(res.analysis);
      window.scrollTo(0, document.body.scrollHeight);
    } catch (e) {
      setOpenError(e.message);
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h1>Analysis History</h1>
        {loading && <p className="muted">Loading history…</p>}
        {error && <div className="alert error">{error}</div>}
        {data && !data.persistent && (
          <div className="alert info">
            Persistent history is unavailable (database not configured). Results below are temporary and will be lost
            when the server restarts — but analysis still works.
          </div>
        )}
        {data && data.items.length === 0 && !loading && (
          <p className="muted">No analyses yet. Upload a capture on the Analyze Traffic page to get started.</p>
        )}
        {data && data.items.length > 0 && (
          <table className="history">
            <thead>
              <tr>
                <th>Date</th>
                <th>File</th>
                <th>Prediction</th>
                <th>Task</th>
                <th>Status</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id}>
                  <td>{formatDateTime(a.createdAt)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ padding: '6px 12px', fontSize: 14 }}
                      onClick={() => view(a.id)}
                    >
                      {a.filename}
                    </button>
                  </td>
                  <td>{a.predictedLabel}</td>
                  <td>{a.task}</td>
                  <td>{a.status || 'completed'}</td>
                  <td>
                    <a href={reportUrl(a.id, 'json')}>JSON</a> · <a href={reportUrl(a.id, 'csv')}>CSV</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {openError && <div className="alert error">{openError}</div>}
      </div>
      {open && <ResultCard analysis={open} />}
    </div>
  );
}
