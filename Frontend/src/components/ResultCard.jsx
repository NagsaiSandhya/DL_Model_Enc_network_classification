import { Link } from 'react-router-dom';
import { reportUrl } from '../services/api.js';
import { formatBytes, formatSeconds, formatDateTime, valueOrUnavailable } from '../utils/format.js';

function pct(x) {
  if (x == null || Number.isNaN(Number(x))) return 'Unavailable';
  return `${(Number(x) * 100).toFixed(1)}%`;
}

export function ProbBars({ probabilities }) {
  if (!probabilities) return <p className="muted">Probabilities unavailable.</p>;
  const entries = Object.entries(probabilities);
  return (
    <div>
      {entries.map(([label, p]) => (
        <div className="bar-row" key={label}>
          <span className="bar-label">{label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(0, Math.min(1, Number(p))) * 100}%` }} />
          </div>
          <span className="bar-value">{pct(p)}</span>
        </div>
      ))}
      <p className="muted" style={{ fontSize: 13 }}>
        Model-estimated probabilities, not guaranteed real-world correctness.
      </p>
    </div>
  );
}

function HistChart({ title, bins, counts, emptyNote }) {
  if (!bins || !counts || counts.every((c) => c === 0)) {
    return (
      <div>
        <h3>{title}</h3>
        <p className="muted">{emptyNote || 'Data unavailable for this capture.'}</p>
      </div>
    );
  }
  const max = Math.max(...counts, 1);
  return (
    <div>
      <h3>{title}</h3>
      {bins.map((b, i) => (
        <div className="bar-row" key={b}>
          <span className="bar-label">{b}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(counts[i] / max) * 100}%` }} />
          </div>
          <span className="bar-value">{counts[i]}</span>
        </div>
      ))}
    </div>
  );
}

export function Charts({ charts }) {
  if (!charts || charts.unavailable) {
    return (
      <div className="card">
        <h2>Traffic Charts</h2>
        <p className="muted">Chart data is unavailable for this capture.</p>
      </div>
    );
  }
  const protos = charts.protocol_distribution;
  return (
    <div className="card">
      <h2>Traffic Charts</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Descriptive packet statistics from the uploaded capture (first {charts.scanned_packets} packets scanned).
      </p>
      {charts.packet_length_hist && (
        <HistChart
          title="Packet length distribution"
          bins={charts.packet_length_hist.bins}
          counts={charts.packet_length_hist.counts}
        />
      )}
      {charts.iat_hist ? (
        <HistChart title="Packet timing distribution" bins={charts.iat_hist.bins} counts={charts.iat_hist.counts} />
      ) : (
        <div>
          <h3>Packet timing distribution</h3>
          <p className="muted">Timing data unavailable for this capture.</p>
        </div>
      )}
      {protos ? (
        <HistChart
          title="Protocol distribution"
          bins={Object.keys(protos)}
          counts={Object.values(protos)}
          emptyNote="Protocol information could not be decoded for this capture."
        />
      ) : (
        <div>
          <h3>Protocol distribution</h3>
          <p className="muted">Protocol information could not be decoded for this capture.</p>
        </div>
      )}
    </div>
  );
}

export default function ResultCard({ analysis }) {
  const isVpn = analysis.predictedLabel === 'vpn';
  return (
    <div>
      <div className={`result-banner ${isVpn ? 'vpn' : 'nonvpn'}`}>
        {isVpn ? 'Likely VPN Traffic' : 'Likely Non-VPN Traffic'}
      </div>
      <p className="muted" style={{ textAlign: 'center' }}>
        The model analyzed the uploaded network capture and predicted whether its traffic resembles VPN or non-VPN
        traffic.
      </p>
      <p className="muted" style={{ textAlign: 'center', fontSize: 13 }}>
        This is a machine-learning prediction, not a guarantee. Accuracy may vary depending on capture quality and how
        closely the traffic resembles the training data.
      </p>

      <div className="card">
        <h2>Summary</h2>
        <div className="grid">
          <div className="stat">
            <div className="label">Predicted class</div>
            <div className="value">{valueOrUnavailable(analysis.predictedLabel)}</div>
          </div>
          <div className="stat">
            <div className="label">Packets processed</div>
            <div className="value">{valueOrUnavailable(analysis.packetCount)}</div>
          </div>
          <div className="stat">
            <div className="label">Feature windows</div>
            <div className="value">{valueOrUnavailable(analysis.featureSampleCount)}</div>
          </div>
          <div className="stat">
            <div className="label">File size</div>
            <div className="value">{formatBytes(analysis.fileSize)}</div>
          </div>
          <div className="stat">
            <div className="label">Processing time</div>
            <div className="value">{formatSeconds(analysis.processingTimeSeconds)}</div>
          </div>
          <div className="stat">
            <div className="label">Model version</div>
            <div className="value">{valueOrUnavailable(analysis.modelVersion)}</div>
          </div>
          <div className="stat">
            <div className="label">Analyzed at</div>
            <div className="value" style={{ fontSize: 15 }}>
              {formatDateTime(analysis.createdAt)}
            </div>
          </div>
          <div className="stat">
            <div className="label">File</div>
            <div className="value" style={{ fontSize: 15 }}>
              {valueOrUnavailable(analysis.filename)}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Class probabilities</h2>
        <ProbBars probabilities={analysis.probabilities} />
      </div>

      <Charts charts={analysis.charts} />

      <details className="technical">
        <summary>Technical Details</summary>
        <p className="muted">Task: {valueOrUnavailable(analysis.task)}</p>
        <p className="muted">
          Window votes: <code className="small">{JSON.stringify(analysis.windowVotes ?? 'Unavailable')}</code>
        </p>
        <p className="muted">Warnings: {(analysis.warnings || []).length ? analysis.warnings.join('; ') : 'None'}</p>
      </details>

      <div className="card" style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <a className="btn" href={reportUrl(analysis.id, 'json')}>
          Download Report (JSON)
        </a>
        <a className="btn secondary" href={reportUrl(analysis.id, 'csv')}>
          Download Report (CSV)
        </a>
        <Link className="btn secondary" to="/analyze">
          Analyze Another File
        </Link>
        <Link className="btn secondary" to="/">
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
