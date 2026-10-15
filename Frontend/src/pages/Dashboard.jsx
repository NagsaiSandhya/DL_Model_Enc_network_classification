import { Link } from 'react-router-dom';
import { useModelInfo, useHistory } from '../hooks/useApi.js';

export default function Dashboard() {
  const { data: model, error: modelError } = useModelInfo();
  const { data: history } = useHistory();
  const recent = history && history.items && history.items[0];

  return (
    <div className="container">
      <div className="card">
        <h1>A Novel Multimodel Deep Learning Framework for Encrypted Traffic Classification</h1>
        <p>
          Analyze network capture files using machine learning. Upload a PCAP file, view the predicted traffic
          category, and download a simple report.
        </p>
        <Link className="btn" to="/analyze">
          Analyze Traffic
        </Link>
      </div>

      <div className="card">
        <h2>How it works</h2>
        <ol className="steps">
          <li>
            <strong>Upload Capture</strong> — choose a .pcap or .pcapng file.
          </li>
          <li>
            <strong>Extract Features</strong> — packet lengths, timing, and protocol statistics (never decrypted
            content).
          </li>
          <li>
            <strong>Run Model</strong> — the trained classifier predicts VPN vs non-VPN traffic.
          </li>
          <li>
            <strong>View Results</strong> — plain-language result, probabilities, charts, and a downloadable report.
          </li>
        </ol>
      </div>

      <div className="card">
        <h2>Supported classification task</h2>
        {modelError ? (
          <div className="alert error">
            Model information is unavailable. Please make sure the backend and ML service are running.
          </div>
        ) : !model ? (
          <p className="muted">Loading model information…</p>
        ) : (
          <div className="grid">
            <div className="stat">
              <div className="label">Task</div>
              <div className="value" style={{ fontSize: 16 }}>
                VPN vs Non-VPN
              </div>
            </div>
            <div className="stat">
              <div className="label">Model</div>
              <div className="value" style={{ fontSize: 16 }}>
                {model.model.model_name} (v{model.model.model_version})
              </div>
            </div>
            <div className="stat">
              <div className="label">Verified test accuracy</div>
              <div className="value">
                {model.model.verified_test_metrics
                  ? `${(model.model.verified_test_metrics.accuracy * 100).toFixed(1)}%`
                  : 'Unavailable'}
              </div>
            </div>
          </div>
        )}
      </div>

      {recent && (
        <div className="card">
          <h2>Most recent analysis</h2>
          <p>
            <strong>{recent.filename}</strong> → <strong>{recent.predictedLabel}</strong>
          </p>
          <Link className="btn secondary" to="/history">
            View History
          </Link>
        </div>
      )}

      <div className="card">
        <h2>Learn more</h2>
        <p className="muted">
          Encrypted traffic classification predicts traffic categories from observable metadata without decrypting
          content.
        </p>
        <Link className="btn secondary" to="/about">
          About Project
        </Link>
      </div>
    </div>
  );
}
