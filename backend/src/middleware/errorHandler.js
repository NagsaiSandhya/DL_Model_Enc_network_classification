// Centralized error handler: friendly messages only, details stay in server logs.
// eslint-disable-next-line no-unused-vars
function errorHandler(err, req, res, next) {
  // eslint-disable-next-line no-console
  console.error('API error:', err && err.message ? err.message : err);
  if (err && err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({ success: false, error: 'This file is larger than the allowed upload limit.' });
  }
  const status = err && err.status && Number.isInteger(err.status) ? err.status : 500;
  const message =
    status === 500
      ? 'Something went wrong on the server. Please try again.'
      : err.message || 'Request failed. Please try again.';
  return res.status(status).json({ success: false, error: message });
}

module.exports = errorHandler;
