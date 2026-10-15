const crypto = require('crypto');
const config = require('../config');
const mlClient = require('../services/mlClient');
const historyStore = require('../services/historyStore');
const { cleanup, sanitize } = require('../middleware/upload');

let active = 0;

async function analyze(req, res, next) {
  if (active >= config.MAX_CONCURRENT_ANALYSES) {
    if (req.file) cleanup(req.file.path);
    return res.status(429).json({ success: false, error: 'The server is busy. Please try again in a moment.' });
  }
  if (!req.file) {
    return res.status(400).json({ success: false, error: 'Please select a PCAP or PCAPNG file.' });
  }
  active += 1;
  const storedPath = req.file.path;
  const originalName = sanitize(req.file.originalname);
  try {
    const a = await mlClient.predictCapture(storedPath, originalName);
    const record = {
      id: crypto.randomUUID(),
      filename: originalName,
      fileSize: req.file.size,
      task: a.task || 'vpn_vs_nonvpn',
      predictedLabel: a.predicted_label,
      probabilities: a.probabilities,
      modelVersion: a.model_version,
      packetCount: a.packet_count,
      featureSampleCount: a.feature_sample_count,
      windowVotes: a.window_votes,
      processingTimeSeconds: a.processing_time_seconds,
      warnings: a.warnings || [],
      charts: a.charts || null,
    };
    const saved = await historyStore.save(record);
    return res.status(200).json({
      success: true,
      analysis: { ...saved.record, persisted: saved.persisted },
      historyPersisted: saved.persisted,
      historyNotice: saved.persisted
        ? undefined
        : 'Analysis completed, but history could not be saved (persistent storage unavailable).',
    });
  } catch (err) {
    return next(err);
  } finally {
    active -= 1;
    cleanup(storedPath);
  }
}

module.exports = { analyze };
