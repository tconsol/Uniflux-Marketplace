import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: resolve(__dirname, '../../.env') });

export const settings = {
  APP_NAME: process.env.APP_NAME || 'MARKETPLACE-SERVICE',
  APP_ENV: process.env.APP_ENV || 'development',
  APP_PORT: parseInt(process.env.APP_PORT || '3085'),

  MONGODB_URI: process.env.MONGODB_URI,
  MONGODB_DB_NAME: process.env.MONGODB_DB_NAME || 'market-place',

  JWT_SECRET: process.env.JWT_SECRET || 'uniflux-super-secret-key-must-be-32-chars-min',
  JWT_ALGORITHM: process.env.JWT_ALGORITHM || 'HS256',

  OPENWEBNINJA_API_KEY: process.env.OPENWEBNINJA_API_KEY || '',

  FETCH_COOLDOWN_MINUTES: 15,
};
