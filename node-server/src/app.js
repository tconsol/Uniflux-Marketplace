import express from 'express';
import { connectDB, closeDB } from './database.js';
import { settings } from './config/settings.js';
import jobsRouter from './routes/jobs.js';
import indeedSchedulerRouter from './routes/indeedScheduler.js';
import { restoreJsearchSchedulers } from './services/jsearchSchedulerService.js';
import { restoreIndeedSchedulers } from './services/indeedSchedulerService.js';

const app = express();
app.use(express.json());

app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.originalUrl} → ${res.statusCode} (${Date.now() - start}ms)`);
  });
  next();
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: settings.APP_NAME, env: settings.APP_ENV });
});

app.use('/api/v1/marketplace/jobs', jobsRouter);
app.use('/api/v1/marketplace/indeed/scheduler', indeedSchedulerRouter);

app.use((req, res) => {
  res.status(404).json({ detail: `Route not found: ${req.method} ${req.originalUrl}` });
});

async function start() {
  await connectDB();
  await restoreJsearchSchedulers();
  await restoreIndeedSchedulers();
  app.listen(settings.APP_PORT, () => {
    console.log(`${settings.APP_NAME} running on port ${settings.APP_PORT}`);
  });
}

process.on('SIGINT', async () => {
  await closeDB();
  process.exit(0);
});

start().catch(err => {
  console.error('Startup error:', err);
  process.exit(1);
});
