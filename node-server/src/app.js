import express from 'express';
import cors from 'cors';
import { connectDB, closeDB } from './database.js';
import { settings } from './config/settings.js';
import jobsRouter from './routes/jobs.js';
import indeedSchedulerRouter from './routes/indeedScheduler.js';
import { restoreJsearchSchedulers } from './services/jsearchSchedulerService.js';
import { restoreIndeedSchedulers } from './services/indeedSchedulerService.js';

const app = express();
app.set('trust proxy', true);

const allowedOrigins = new Set(settings.ALLOWED_ORIGINS);

app.use(cors({
  origin(origin, callback) {
    if (!origin) return callback(null, true);
    if (allowedOrigins.has(origin)) return callback(null, true);
    return callback(new Error(`CORS blocked for origin: ${origin}`));
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: [
    'Content-Type',
    'Authorization',
    'X-Org-Id',
    'X-User-Id',
    'X-User-Email',
    'X-User-Role',
  ],
}));

app.use(express.json({ limit: '2mb' }));

app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    console.log(JSON.stringify({
      ts: new Date().toISOString(),
      method: req.method,
      path: req.originalUrl,
      status: res.statusCode,
      duration_ms: Date.now() - start,
      ip: req.ip,
    }));
  });
  next();
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: settings.APP_NAME,
    env: settings.APP_ENV,
    uptime: process.uptime(),
  });
});

app.get('/ready', (req, res) => {
  res.json({ status: 'ready' });
});

app.use('/api/v1/marketplace/jobs', jobsRouter);
app.use('/api/v1/marketplace/indeed/scheduler', indeedSchedulerRouter);

app.use((req, res) => {
  res.status(404).json({ detail: `Route not found: ${req.method} ${req.originalUrl}` });
});

app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);

  if (err.message?.startsWith('CORS blocked')) {
    return res.status(403).json({ detail: err.message });
  }

  return res.status(500).json({ detail: 'Internal server error' });
});

async function start() {
  await connectDB();

  if (settings.APP_ENV !== 'production') {
    await restoreJsearchSchedulers();
    await restoreIndeedSchedulers();
  } else {
    console.log('Skipping in-memory cron restore in production on Cloud Run');
  }

  const port = settings.APP_PORT;
  app.listen(port, '0.0.0.0', () => {
    console.log(`${settings.APP_NAME} running on 0.0.0.0:${port} env=${settings.APP_ENV}`);
  });
}

async function shutdown(signal) {
  console.log(`Received ${signal}, shutting down`);
  try {
    await closeDB();
  } finally {
    process.exit(0);
  }
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

start().catch(err => {
  console.error('Startup error:', err);
  process.exit(1);
});