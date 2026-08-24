const request = require('supertest');
const app = require('./index');

describe('GET /health', () => {
  it('returns 200 with status ok', async () => {
    const res = await request(app).get('/health');
    expect(res.statusCode).toBe(200);
    expect(res.body).toEqual({ status: 'ok' });
  });
});

describe('GET /metrics', () => {
  it('returns 200 with runtime stats', async () => {
    const res = await request(app).get('/metrics');
    expect(res.statusCode).toBe(200);
    expect(res.body).toHaveProperty('uptime_seconds');
    expect(res.body).toHaveProperty('memory_mb');
    expect(res.body).toHaveProperty('node_version');
  });
});

describe('POST /data', () => {
  it('echoes back a valid JSON payload', async () => {
    const payload = { shipment_id: 'KOR-001', status: 'in_transit' };
    const res = await request(app).post('/data').send(payload);
    expect(res.statusCode).toBe(200);
    expect(res.body.received).toEqual(payload);
  });

  it('returns 400 for an empty body', async () => {
    const res = await request(app).post('/data').send({});
    expect(res.statusCode).toBe(400);
  });
});
