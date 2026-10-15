function buildReport(record) {
  return {
    analysisId: record.id,
    timestamp: record.createdAt,
    filename: record.filename,
    fileSizeBytes: record.fileSize,
    task: record.task,
    predictedClass: record.predictedLabel,
    probabilities: record.probabilities,
    modelVersion: record.modelVersion,
    packetCount: record.packetCount ?? 'Unavailable',
    featureSampleCount: record.featureSampleCount ?? 'Unavailable',
    processingDurationSeconds: record.processingTimeSeconds ?? 'Unavailable',
    warnings: record.warnings || [],
    disclaimer:
      'This is a machine-learning prediction, not a guarantee. Accuracy may vary depending on capture quality and how closely the traffic resembles the training data.',
  };
}

function toCsv(report) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const rows = [
    ['field', 'value'],
    ['analysisId', report.analysisId],
    ['timestamp', report.timestamp],
    ['filename', report.filename],
    ['fileSizeBytes', report.fileSizeBytes],
    ['task', report.task],
    ['predictedClass', report.predictedClass],
    ['probabilities', JSON.stringify(report.probabilities)],
    ['modelVersion', report.modelVersion],
    ['packetCount', report.packetCount],
    ['featureSampleCount', report.featureSampleCount],
    ['processingDurationSeconds', report.processingDurationSeconds],
    ['warnings', (report.warnings || []).join('; ')],
    ['disclaimer', report.disclaimer],
  ];
  return rows.map((r) => r.map(esc).join(',')).join('\n');
}

module.exports = { buildReport, toCsv };
