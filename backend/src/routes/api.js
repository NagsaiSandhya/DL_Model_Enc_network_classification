const express = require('express');
const mlClient = require('../services/mlClient');
const historyStore = require('../services/historyStore');
const { analyze } = require('../controllers/analyzeController');
const { listAnalyses, getAnalysis, downloadReport } = require('../controllers/historyController');
const { upload } = require('../middleware/upload');

const router = express.Router();

router.get('/health', async (req, res) => {
  const mlReachable = await mlClient.checkMlReachable();
  res.json({ status: 'ok', mlServiceReachable: mlReachable, historyPersistent: historyStore.isPersistent() });
});

router.get('/model-info', async (req, res, next) => {
  try {
    const info = await mlClient.fetchModelInfo();
    if (!info) return res.status(503).json({ success: false, error: 'The machine learning service is unavailable. Please try again later.' });
    res.json({ success: true, model: info });
  } catch (err) {
    next(err);
  }
});

router.post('/analyze', upload.single('file'), analyze);
router.get('/analysis', listAnalyses);
router.get('/analysis/:id', getAnalysis);
router.get('/analysis/:id/report', downloadReport);

module.exports = router;
