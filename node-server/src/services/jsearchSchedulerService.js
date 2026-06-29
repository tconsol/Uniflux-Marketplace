import cron from 'node-cron';
import { getDB } from '../database.js';
import { searchAndStoreJsearchJobs } from './jobsService.js';
import { settings } from '../config/settings.js';

const schedulerJobs = new Map();

function cronEnabled() {
  return settings.APP_ENV !== 'production';
}

export async function restoreJsearchSchedulers() {
  if (!cronEnabled()) {
    console.log('[JSearch Scheduler] skipped restore in production (Cloud Run stateless mode)');
    return;
  }

  const db = getDB();
  const active = await db.collection('jsearch_scheduler_meta')
    .find({ enabled: true })
    .toArray();

  for (const state of active) {
    if (!state.config) continue;
    const orgId = state.org_id;
    const config = state.config;
    const jobId = `jsearch_auto_pull:${orgId}`;
    const cronExpr = intervalToCron(config.interval_minutes || 60);
    const task = cron.schedule(cronExpr, () => runJsearchTick(orgId), { timezone: 'UTC' });
    schedulerJobs.set(jobId, task);
    console.log(`[JSearch Scheduler] restored org_id=${orgId} interval=${config.interval_minutes}min`);
  }

  console.log(`[JSearch Scheduler] restored ${active.length} scheduler(s)`);
}

async function saveSchedulerState(orgId, enabled, config = null, lastRunAt = null, lastResult = null) {
  const db = getDB();
  const update = { enabled, updated_at: new Date() };
  if (config) update.config = config;
  if (lastRunAt) update.last_run_at = lastRunAt;
  if (lastResult) update.last_result = lastResult;

  await db.collection('jsearch_scheduler_meta').updateOne(
    { org_id: orgId },
    { $set: update },
    { upsert: true }
  );
}

async function getSchedulerState(orgId) {
  const db = getDB();
  return db.collection('jsearch_scheduler_meta').findOne({ org_id: orgId });
}

async function runJsearchTick(orgId) {
  const state = await getSchedulerState(orgId);
  if (!state?.enabled || !state?.config) return;

  const config = state.config;
  let totalFetched = 0;
  let totalNew = 0;
  let totalStored = 0;
  const errors = [];

  for (const keyword of config.keywords || []) {
    try {
      const result = await searchAndStoreJsearchJobs({
        keywords: keyword,
        location: config.location,
        country: config.country,
        language: config.language,
        numPages: config.num_pages,
        datePosted: config.date_posted,
        workFromHome: config.work_from_home,
        employmentTypes: config.employment_types,
        jobRequirements: config.job_requirements,
        radius: config.radius,
        excludeJobPublishers: config.exclude_job_publishers,
        useCursor: config.use_cursor,
      }, orgId);

      totalFetched += result.fetched_count;
      totalStored += result.stored_count;
      totalNew += result.new_count;
    } catch (err) {
      errors.push({ keyword, error: err.message });
    }
  }

  await saveSchedulerState(orgId, true, null, new Date(), {
    total_fetched: totalFetched,
    total_stored: totalStored,
    total_new: totalNew,
    keywords_run: (config.keywords || []).length,
    errors,
  });
}

function intervalToCron(minutes) {
  if (minutes < 60) return `*/${minutes} * * * *`;
  const hours = Math.floor(minutes / 60);
  return `0 */${hours} * * *`;
}

export async function startJsearchSchedulerForOrg(orgId, config) {
  const jobId = `jsearch_auto_pull:${orgId}`;

  if (!cronEnabled()) {
    await saveSchedulerState(orgId, true, config);
    return {
      enabled: true,
      running: false,
      mode: 'persistent-state-only',
      job_id: jobId,
      interval_minutes: config.interval_minutes,
      next_run_at: null,
      last_run_at: null,
      last_result: null,
      config,
      message: 'Scheduler state saved, but in-memory cron is disabled in production on Cloud Run.',
    };
  }

  if (schedulerJobs.has(jobId)) {
    schedulerJobs.get(jobId).stop();
    schedulerJobs.delete(jobId);
  }

  const cronExpr = intervalToCron(config.interval_minutes);
  const task = cron.schedule(cronExpr, () => runJsearchTick(orgId), { timezone: 'UTC' });
  schedulerJobs.set(jobId, task);

  await saveSchedulerState(orgId, true, config);

  return {
    enabled: true,
    running: true,
    mode: 'in-memory-cron',
    job_id: jobId,
    interval_minutes: config.interval_minutes,
    next_run_at: null,
    last_run_at: null,
    last_result: null,
    config,
  };
}

export async function stopJsearchSchedulerForOrg(orgId) {
  const jobId = `jsearch_auto_pull:${orgId}`;

  if (schedulerJobs.has(jobId)) {
    schedulerJobs.get(jobId).stop();
    schedulerJobs.delete(jobId);
  }

  const state = await getSchedulerState(orgId);
  await saveSchedulerState(orgId, false);

  return {
    enabled: false,
    running: false,
    mode: cronEnabled() ? 'in-memory-cron' : 'persistent-state-only',
    job_id: jobId,
    interval_minutes: state?.config?.interval_minutes || 60,
    next_run_at: null,
    last_run_at: state?.last_run_at || null,
    last_result: state?.last_result || null,
    config: state?.config || null,
  };
}

export async function getJsearchSchedulerStatusForOrg(orgId) {
  const jobId = `jsearch_auto_pull:${orgId}`;
  const state = await getSchedulerState(orgId);

  return {
    enabled: Boolean(state?.enabled),
    running: cronEnabled() ? schedulerJobs.has(jobId) : false,
    mode: cronEnabled() ? 'in-memory-cron' : 'persistent-state-only',
    job_id: jobId,
    interval_minutes: state?.config?.interval_minutes || 60,
    next_run_at: null,
    last_run_at: state?.last_run_at || null,
    last_result: state?.last_result || null,
    config: state?.config || null,
  };
}