const express = require('express');
const client = require('prom-client');

const app = express();
const PORT = process.env.PORT || 3002;

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

const shipments = {
  'SHP-001': { status: 'in_transit', location: 'Accra' },
  'SHP-002': { status: 'delivered', location: 'Kumasi' },
};

app.get('/health', (req, res) => res.json({ status: 'ok', service: 'tracking-service' }));
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.get('/track/:id', (req, res) => {
  const shipment = shipments[req.params.id];
  if (!shipment) return res.status(404).json({ error: 'Shipment not found' });
  res.json({ id: req.params.id, ...shipment });
});

app.patch('/track/:id', (req, res) => {
  if (!shipments[req.params.id]) return res.status(404).json({ error: 'Shipment not found' });
  shipments[req.params.id] = { ...shipments[req.params.id], ...req.body };
  res.json({ id: req.params.id, ...shipments[req.params.id] });
});

app.listen(PORT, () => console.log(JSON.stringify({ level: 'info', service: 'tracking-service', msg: `Listening on port ${PORT}` })));
module.exports = app;
