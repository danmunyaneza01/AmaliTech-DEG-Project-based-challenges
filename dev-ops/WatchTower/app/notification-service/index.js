const express = require('express');
const client = require('prom-client');

const app = express();
const PORT = process.env.PORT || 3003;

const register = new client.Registry();
client.collectDefaultMetrics({ register });

const httpRequests = new client.Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'route', 'status'],
  registers: [register],
});

app.use(express.json());
app.use((req, res, next) => {
  res.on('finish', () => {
    httpRequests.inc({ method: req.method, route: req.path, status: res.statusCode });
  });
  next();
});

app.get('/health', (req, res) => res.json({ status: 'ok', service: 'notification-service' }));
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.post('/notify', (req, res) => {
  const { recipient, message } = req.body;
  if (!recipient || !message) return res.status(400).json({ error: 'recipient and message are required' });
  console.log(JSON.stringify({ level: 'info', service: 'notification-service', event: 'notification_sent', recipient, message }));
  res.status(202).json({ queued: true, recipient });
});

app.listen(PORT, () => console.log(JSON.stringify({ level: 'info', service: 'notification-service', msg: `Listening on port ${PORT}` })));
module.exports = app;
