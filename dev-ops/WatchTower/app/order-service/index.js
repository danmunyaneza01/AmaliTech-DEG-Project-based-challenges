const express = require('express');
const client = require('prom-client');

const app = express();
const PORT = process.env.PORT || 3001;

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

const orders = [];

app.get('/health', (req, res) => res.json({ status: 'ok', service: 'order-service' }));
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.get('/orders', (req, res) => res.json(orders));
app.post('/orders', (req, res) => {
  const { item, quantity } = req.body;
  if (!item || !quantity) return res.status(400).json({ error: 'item and quantity are required' });
  const order = { id: `ORD-${Date.now()}`, item, quantity, status: 'pending' };
  orders.push(order);
  res.status(201).json(order);
});

app.listen(PORT, () => console.log(JSON.stringify({ level: 'info', service: 'order-service', msg: `Listening on port ${PORT}` })));
module.exports = app;
