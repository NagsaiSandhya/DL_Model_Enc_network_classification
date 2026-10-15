const mongoose = require('mongoose');

const AnalysisSchema = new mongoose.Schema(
  {
    analysisId: { type: String, required: true, unique: true },
    filename: { type: String, required: true },
    fileSize: { type: Number },
    task: { type: String, default: 'vpn_vs_nonvpn' },
    predictedLabel: { type: String },
    probabilities: { type: Map, of: Number },
    modelVersion: { type: String },
    packetCount: { type: Number },
    featureSampleCount: { type: Number },
    processingTimeSeconds: { type: Number },
    warnings: [{ type: String }],
    charts: { type: mongoose.Schema.Types.Mixed },
    status: { type: String, default: 'completed' },
  },
  { timestamps: true }
);

module.exports = mongoose.models.Analysis || mongoose.model('Analysis', AnalysisSchema);
