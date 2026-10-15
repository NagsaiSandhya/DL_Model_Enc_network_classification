const express = require('express');
const cors = require('cors');
const config = require('./config');
const apiRoutes = require('./routes/api');
const errorHandler = require('./middleware/errorHandler');
const historyStore = require('./services/historyStore');

const app = express();

app.use(cors({ origin: config.FRONTEND_ORIGIN }));
app.use(express.json({ limit: '1mb' }));

app.use('/api', apiRoutes);

app.use((req, res) => res.status(404).json({ success: false, error: 'Not found.' }));
app.use(errorHandler);

let serverHandle = null;

async function start() {
  await historyStore.init();
  await new Promise((resolve) => {
    serverHandle = app.listen(config.PORT, () => {
      // eslint-disable-next-line no-console
      console.log(`Backend listening on http://localhost:${config.PORT}`);
      resolve();
    });
  });
}

function close() {
  return new Promise((resolve) => {
    if (serverHandle) serverHandle.close(() => resolve());
    else resolve();
  });
}

if (require.main === module) {
  start();
}

module.exports = { app, start, close };
