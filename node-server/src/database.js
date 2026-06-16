import { MongoClient } from 'mongodb';
import { settings } from './config/settings.js';

let client = null;

export async function connectDB() {
  if (!client) {
    client = new MongoClient(settings.MONGODB_URI);
    await client.connect();
    console.log('MongoDB connected');
    await ensureIndexes();
  }
  return client;
}

async function ensureIndexes() {
  const db = client.db(settings.MONGODB_DB_NAME);
  const coll = db.collection('scraped_jobs');
  await Promise.all([
    coll.createIndex({ scraped_at: -1 }),
    coll.createIndex({ source_site: 1 }),
    coll.createIndex({ org_id: 1 }),
    coll.createIndex({ job_type: 1 }),
    coll.createIndex({ 'location.raw': 1 }),
    coll.createIndex({ skills: 1 }),
    coll.createIndex({ org_id: 1, source_site: 1 }),
    coll.createIndex({ org_id: 1, scraped_at: -1 }),
  ]);
  console.log('MongoDB indexes ensured');
}

export function getDB() {
  if (!client) throw new Error('DB not connected. Call connectDB() first.');
  return client.db(settings.MONGODB_DB_NAME);
}

export async function closeDB() {
  if (client) {
    await client.close();
    client = null;
  }
}
