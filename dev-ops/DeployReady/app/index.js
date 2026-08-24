const express = require('express');

const app = express();
const PORT = process.env.PORT || 3000;
const startTime = Date.now();

app.use(express.json());

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

app.get('/metrics', (req, res) => {
  const uptimeSeconds = Math.floor((Date.now() - startTime) / 1000);
  res.status(200).json({
    uptime_seconds: uptimeSeconds,
    memory_mb: Math.round(process.memoryUsage().rss / 1024 / 1024),
    node_version: process.version,
  });
});

app.post('/data', (req, res) => {
  const payload = req.body;
  if (!payload || Object.keys(payload).length === 0) {
    return res.status(400).json({ error: 'Request body must be a non-empty JSON object.' });
  }
  res.status(200).json({ received: payload });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
