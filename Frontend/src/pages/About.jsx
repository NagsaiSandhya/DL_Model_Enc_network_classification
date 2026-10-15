export default function About() {
  return (
    <div className="container">
      <div className="card">
        <h1>About Project</h1>
        <h2>The research problem</h2>
        <p>
          Most internet traffic is encrypted, so traditional inspection cannot read its content. Encrypted traffic
          classification predicts traffic categories from observable metadata — packet sizes, timing, and protocol
          patterns — without decrypting anything.
        </p>
        <h2>How the application processes a capture</h2>
        <ol className="steps">
          <li>
            <strong>Upload Capture</strong> — your .pcap/.pcapng file is validated and stored temporarily.
          </li>
          <li>
            <strong>Extract Features</strong> — 24 windowed statistics (lengths, inter-arrival times, TCP/UDP ratios,
            flags, direction) using the same pipeline as training.
          </li>
          <li>
            <strong>Run Model</strong> — a Random Forest (v1.0.0, verified test accuracy 96.3%) votes per window.
          </li>
          <li>
            <strong>View Results</strong> — majority prediction with per-class scores, charts, and a report.
          </li>
        </ol>
        <h2>Currently supported task</h2>
        <p>
          <strong>VPN vs non-VPN classification only.</strong> The model does not identify individual applications
          (chat, email, video, …) even though such traffic appears in the dataset.
        </p>
        <h2>Limitations</h2>
        <ul className="steps">
          <li>Predictions are estimates; accuracy varies with capture quality and similarity to training data.</li>
          <li>Only the first 20,000 packets per capture are analyzed (same rule as training).</li>
          <li>Class scores are raw model vote fractions, not calibrated probabilities.</li>
          <li>The application never decrypts traffic and cannot reveal exact user activity.</li>
        </ul>
        <h2>Future work</h2>
        <p className="muted">
          Validated application-level classification and a multimodel deep-learning comparison (a 1D-CNN on packet
          sequences already exists as an experimental second model).
        </p>
      </div>
    </div>
  );
}
