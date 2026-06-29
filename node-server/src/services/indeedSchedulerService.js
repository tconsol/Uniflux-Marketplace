import cron from 'node-cron';
import { getDB } from '../database.js';
import { settings } from '../config/settings.js';

const schedulerJobs = new Map();

function cronEnabled() {
  return settings.APP_ENV !== 'production';
}

export async function restoreIndeedSchedulers() {
  if (!cronEnabled()) {
    console.log('[Indeed Scheduler] skipped restore in production (Cloud Run stateless mode)');
    return;
  }

  const db = getDB();
  const active = await db.collection('indeed_scheduler_meta')
    .find({ enabled: true })
    .toArray();

  for (const state of active) {
    if (!state.config) continue;
    const orgId = state.org_id;
    const config = state.config;
    const jobId = `indeed_auto_pull:${orgId}`;
    const cronExpr = intervalToCron(config.interval_minutes || 2);
    const task = cron.schedule(cronExpr, () => runIndeedTick(orgId), { timezone: 'UTC' });
    schedulerJobs.set(jobId, task);
    console.log(`[Indeed Scheduler] restored org_id=${orgId} interval=${config.interval_minutes}min`);
  }

  console.log(`[Indeed Scheduler] restored ${active.length} scheduler(s)`);
}

async function saveSchedulerState(
  orgId,
  enabled,
  config = null,
  lastRunAt = null,
  lastResult = null,
  currentKeywordIndex = null,
  lastKeyword = null
) {
  const db = getDB();
  const update = { enabled, updated_at: new Date() };

  if (config !== null) update.config = config;
  if (lastRunAt !== null) update.last_run_at = lastRunAt;
  if (lastResult !== null) update.last_result = lastResult;
  if (currentKeywordIndex !== null) update.current_keyword_index = currentKeywordIndex;
  if (lastKeyword !== null) update.last_keyword = lastKeyword;

  await db.collection('indeed_scheduler_meta').updateOne(
    { org_id: orgId },
    { $set: update },
    { upsert: true }
  );
}

async function getSchedulerState(orgId) {
  return getDB().collection('indeed_scheduler_meta').findOne({ org_id: orgId });
}

async function runIndeedTick(orgId) {
  const state = await getSchedulerState(orgId);
  if (!state?.enabled || !state?.config) {
    console.log(`[Indeed Scheduler] tick skipped org_id=${orgId} — disabled`);
    return;
  }

  const config = state.config;
  const keywords = (config.keywords || []).map(k => k.trim()).filter(Boolean);

  if (!keywords.length) {
    await saveSchedulerState(
      orgId,
      true,
      null,
      new Date(),
      { total_fetched: 0, keyword_ran: null, error: 'No keywords configured' }
    );
    return;
  }

  const currentIndex = (parseInt(state.current_keyword_index, 10) || 0) % keywords.length;
  const keyword = keywords[currentIndex];
  const nextIndex = (currentIndex + 1) % keywords.length;

  console.log(`[Indeed Scheduler] tick org_id=${orgId} keyword=${keyword} index=${currentIndex}`);

  const lastResult = {
    total_fetched: 0,
    keyword_ran: keyword,
    keyword_index_ran: currentIndex,
    next_keyword_index: nextIndex,
    errors: [{ keyword, error: 'Indeed scraping requires Python/JobSpy — not available in Node server' }],
  };

  await saveSchedulerState(orgId, true, null, new Date(), lastResult, nextIndex, keyword);
}

function intervalToCron(minutes) {
  if (minutes < 60) return `*/${minutes} * * * *`;
  const hours = Math.floor(minutes / 60);
  return `0 */${hours} * * *`;
}

export async function startIndeedSchedulerForOrg(orgId, config) {
  const jobId = `indeed_auto_pull:${orgId}`;
  const state = await getSchedulerState(orgId);
  const currentKeywordIndex = parseInt(state?.current_keyword_index, 10) || 0;
  const lastRunAt = state?.last_run_at || null;
  const lastResult = state?.last_result || null;

  if (!cronEnabled()) {
    await saveSchedulerState(orgId, true, config, lastRunAt, lastResult, currentKeywordIndex);
    return {
      enabled: true,
      running: false,
      mode: 'persistent-state-only',
      job_id: jobId,
      interval_minutes: config.interval_minutes,
      next_run_at: null,
      last_run_at: lastRunAt,
      last_result: lastResult,
      config,
      message: 'Scheduler state saved, but in-memory cron is disabled in production on Cloud Run.',
    };
  }

  if (schedulerJobs.has(jobId)) {
    schedulerJobs.get(jobId).stop();
    schedulerJobs.delete(jobId);
  }

  const task = cron.schedule(intervalToCron(config.interval_minutes), () => runIndeedTick(orgId), { timezone: 'UTC' });
  schedulerJobs.set(jobId, task);

  await saveSchedulerState(orgId, true, config, lastRunAt, lastResult, currentKeywordIndex);

  return {
    enabled: true,
    running: true,
    mode: 'in-memory-cron',
    job_id: jobId,
    interval_minutes: config.interval_minutes,
    next_run_at: null,
    last_run_at: lastRunAt,
    last_result: lastResult,
    config,
  };
}

export async function stopIndeedSchedulerForOrg(orgId) {
  const jobId = `indeed_auto_pull:${orgId}`;

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
    interval_minutes: state?.config?.interval_minutes || 2,
    next_run_at: null,
    last_run_at: state?.last_run_at || null,
    last_result: state?.last_result || null,
    config: state?.config || null,
  };
}

export async function getIndeedSchedulerStatusForOrg(orgId) {
  const jobId = `indeed_auto_pull:${orgId}`;
  const state = await getSchedulerState(orgId);

  return {
    enabled: Boolean(state?.enabled),
    running: cronEnabled() ? schedulerJobs.has(jobId) : false,
    mode: cronEnabled() ? 'in-memory-cron' : 'persistent-state-only',
    job_id: jobId,
    interval_minutes: state?.config?.interval_minutes || 2,
    next_run_at: null,
    last_run_at: state?.last_run_at || null,
    last_result: state?.last_result || null,
    config: state?.config || null,
  };
}