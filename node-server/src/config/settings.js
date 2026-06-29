import dotenv from 'dotenv';

const isCloudRun = Boolean(process.env.K_SERVICE || process.env.PORT);

if (!isCloudRun) {
  dotenv.config();
}

function required(name, fallback = undefined) {
  const value = process.env[name] ?? fallback;
  if (value === undefined || value === null || value === '') {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function parseList(value, fallback = '') {
  return String(value ?? fallback)
    .split(',')
    .map(v => v.trim())
    .filter(Boolean);
}

function parsePort(value, fallback = 8080) {
  const parsed = Number.parseInt(String(value ?? fallback), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function resolveAppEnv() {
  if (process.env.APP_ENV) return process.env.APP_ENV;
  if (isCloudRun) return 'production';
  return 'development';
}

export const settings = {
  APP_NAME: process.env.APP_NAME || 'MARKETPLACE-SERVICE',
  APP_ENV: resolveAppEnv(),
  APP_PORT: parsePort(process.env.PORT || process.env.APP_PORT, 8080),

  MONGODB_URI: required('MONGODB_URI'),
  MONGODB_DB_NAME: process.env.MONGODB_DB_NAME || 'market-place',

  JWT_SECRET: required('JWT_SECRET'),
  JWT_ALGORITHM: process.env.JWT_ALGORITHM || 'HS256',

  OPENWEBNINJA_API_KEY: process.env.OPENWEBNINJA_API_KEY || '',

  FRONTEND_URL: process.env.FRONTEND_URL || '',
  ALLOWED_ORIGINS: parseList(
    process.env.ALLOWED_ORIGINS,
    process.env.FRONTEND_URL || 'http://localhost:5173,http://localhost:5175'
  ),

  FETCH_COOLDOWN_MINUTES: Number.parseInt(process.env.FETCH_COOLDOWN_MINUTES || '15', 10) || 15,
};