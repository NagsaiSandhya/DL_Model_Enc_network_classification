const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const multer = require('multer');
const config = require('../config');

const TMP_DIR = path.join(__dirname, '..', '..', 'tmp', 'uploads');

function sanitize(name) {
  const base = path.basename(String(name || 'capture.pcap'));
  return base.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 120) || 'capture.pcap';
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    fs.mkdirSync(TMP_DIR, { recursive: true });
    cb(null, TMP_DIR);
  },
  filename: (req, file, cb) => {
    const ext = path.extname(sanitize(file.originalname)).toLowerCase();
    cb(null, `${Date.now()}-${crypto.randomBytes(8).toString('hex')}${ext}`);
  },
});

function fileFilter(req, file, cb) {
  const ext = path.extname(String(file.originalname || '')).toLowerCase();
  if (ext === '.pcap' || ext === '.pcapng') return cb(null, true);
  const err = new Error('Please select a PCAP or PCAPNG file.');
  err.status = 400;
  cb(err);
}

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: config.MAX_FILE_BYTES, files: 1 },
});

function cleanup(filePath) {
  if (!filePath) return;
  fs.unlink(filePath, () => {});
}

module.exports = { upload, cleanup, sanitize, TMP_DIR };
