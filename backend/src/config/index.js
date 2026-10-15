require('dotenv').config();

const PORT = parseInt(process.env.PORT || '5000', 10);
const ML_SERVICE_URL = (process.env.ML_SERVICE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || 'http://localhost:5173';
const MAX_FILE_MB = parseInt(process.env.MAX_FILE_MB || '200', 10);
const ML_TIMEOUT_MS = parseInt(process.env.ML_TIMEOUT_MS || '240000', 10);
const MAX_CONCURRENT_ANALYSES = parseInt(process.env.MAX_CONCURRENT_ANALYSES || '4', 10);
const MONGODB_URI = process.env.MONGODB_URI || '';

module.exports = {
  PORT,
  ML_SERVICE_URL,
  FRONTEND_ORIGIN,
  MAX_FILE_MB,
  MAX_FILE_BYTES: MAX_FILE_MB * 1024 * 1024,
  ML_TIMEOUT_MS,
  MAX_CONCURRENT_ANALYSES,
  MONGODB_URI,
};
