const historyStore = require('../services/historyStore');
const { buildReport, toCsv } = require('../utils/reports');

async function listAnalyses(req, res, next) {
  try {
    const { items, persistent } = await historyStore.list();
    return res.json({ success: true, items, persistent });
  } catch (err) {
    return next(err);
  }
}

async function getAnalysis(req, res, next) {
  try {
    const found = await historyStore.getById(req.params.id);
    if (!found) return res.status(404).json({ success: false, error: 'Analysis not found.' });
    return res.json({ success: true, analysis: found.record });
  } catch (err) {
    return next(err);
  }
}

async function downloadReport(req, res, next) {
  try {
    const found = await historyStore.getById(req.params.id);
    if (!found) return res.status(404).json({ success: false, error: 'Analysis not found.' });
    const report = buildReport(found.record);
    const format = String(req.query.format || 'json').toLowerCase();
    const base = `traffic-report-${report.analysisId}`;
    if (format === 'csv') {
      res.setHeader('Content-Type', 'text/csv');
      res.setHeader('Content-Disposition', `attachment; filename="${base}.csv"`);
      return res.send(toCsv(report));
    }
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Content-Disposition', `attachment; filename="${base}.json"`);
    return res.send(JSON.stringify(report, null, 2));
  } catch (err) {
    return next(err);
  }
}

module.exports = { listAnalyses, getAnalysis, downloadReport };
