import { ObjectId } from 'mongodb';
import { getDB } from '../database.js';
import { settings } from '../config/settings.js';
import { jsearchSearch, jsearchSearchV2 } from './jsearchService.js';

const COOLDOWN_MS = settings.FETCH_COOLDOWN_MINUTES * 60 * 1000;

function flexibleRegex(value) {
  const normalized = value.trim().toLowerCase();
  const words = normalized.split(/[\s\-_]+/).filter(Boolean);
  const pattern = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[\\s\\-_]*');
  return pattern;
}

const JOB_TYPE_MAP = {
  fulltime:        ['full.?time', 'full_time', 'permanent'],
  parttime:        ['part.?time', 'part_time'],
  contract:        ['contract(?!_to_hire)', 'contractor', 'freelance', 'c2c', 'corp.?to.?corp', 'w2', 'c2h'],
  contract_to_hire:['contract.?to.?hire', 'c2h', 'contract_to_hire'],
  internship:      ['intern(?:ship)?'],
  temporary:       ['temp(?:orary)?'],
  perdiem:         ['per.?diem'],
};

export function normalizeJobType(raw) {
  if (!raw) return null;
  const lower = raw.trim().toLowerCase();
  for (const [standard, patterns] of Object.entries(JOB_TYPE_MAP)) {
    for (const p of patterns) {
      if (new RegExp(`^${p}$`, 'i').test(lower) || new RegExp(p, 'i').test(lower)) {
        return standard;
      }
    }
  }
  return lower.replace(/[\s\-]+/g, '_');
}

function buildQuery({ orgId, keyword, location, jobType, site, skills }) {
  const query = {};
  const andConditions = [];

  if (orgId) query.org_id = orgId;

  if (keyword) {
    andConditions.push({ $or: [
      { title: { $regex: flexibleRegex(keyword), $options: 'i' } },
      { company_name: { $regex: flexibleRegex(keyword), $options: 'i' } },
      { description: { $regex: flexibleRegex(keyword), $options: 'i' } },
    ]});
  }

  if (location) query['location.raw'] = { $regex: flexibleRegex(location), $options: 'i' };
  if (jobType) query.job_type = { $regex: flexibleRegex(jobType), $options: 'i' };
  if (site) query.source_site = site.trim().toLowerCase();

  if (skills) {
    const skillList = skills.split(',').map(s => s.trim()).filter(Boolean);
    if (skillList.length) {
      andConditions.push({ $or: skillList.map(s => ({
        $or: [
          { skills: { $regex: flexibleRegex(s), $options: 'i' } },
          { title: { $regex: flexibleRegex(s), $options: 'i' } },
          { description: { $regex: flexibleRegex(s), $options: 'i' } },
        ]
      }))});
    }
  }

  if (andConditions.length) query.$and = andConditions;
  return query;
}

export async function getPublicJobs({ keyword, location, jobType, site, skills, cursor = null, limit = 200 }) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');
  const query = buildQuery({ orgId: null, keyword, location, jobType, site, skills });

  if (cursor) {
    try { query._id = { $gt: new ObjectId(cursor) }; } catch {}
  }

  console.log(`[Jobs] getPublicJobs cursor=${cursor} limit=${limit}`);

  const docs = await coll.find(query).sort({ _id: 1 }).limit(limit).toArray();
  const nextCursor = docs.length === limit ? docs[docs.length - 1]._id.toString() : null;

  return {
    count: docs.length,
    next_cursor: nextCursor,
    has_more: nextCursor !== null,
    jobs: docs.map(docToJob),
  };
}

export async function getPublicJobsCount({ keyword, location, jobType, site, skills }) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');
  const query = buildQuery({ orgId: null, keyword, location, jobType, site, skills });

  const [total, siteAgg, jobTypeAgg] = await Promise.all([
    coll.countDocuments(query),
    coll.aggregate([{ $match: query }, { $group: { _id: '$source_site', count: { $sum: 1 } } }]).toArray(),
    coll.aggregate([{ $match: query }, { $group: { _id: '$job_type', count: { $sum: 1 } } }]).toArray(),
  ]);

  return {
    total,
    by_site: Object.fromEntries(siteAgg.filter(r => r._id).map(r => [r._id, r.count])),
    by_job_type: Object.fromEntries(jobTypeAgg.filter(r => r._id).map(r => [r._id, r.count])),
  };
}

function docToJob(doc) {
  return {
    id: doc._id?.toString(),
    org_id: doc.org_id,
    source_site: doc.source_site || '',
    external_id: doc.external_id || null,
    title: doc.title || null,
    company_name: doc.company_name || null,
    company_url: doc.company_url || null,
    location: doc.location || {},
    salary: doc.salary || {},
    job_type: normalizeJobType(doc.job_type),
    description: doc.description || null,
    posted_at: doc.posted_at || null,
    url: doc.url || null,
    skills: doc.skills || [],
    scraped_at: doc.scraped_at || doc.created_at || new Date(),
  };
}

function jsearchRawToJob(raw, orgId) {
  const locationRaw = raw.job_location ||
    [raw.job_city, raw.job_state, raw.job_country].filter(Boolean).join(', ') || null;

  const isRemote = Boolean(raw.job_is_remote) || raw.work_arrangement === 'remote';

  let postedAt = null;
  if (raw.job_posted_at_datetime_utc) {
    try { postedAt = new Date(raw.job_posted_at_datetime_utc); } catch {}
  }

  const skills = [
    ...(Array.isArray(raw.required_technologies) ? raw.required_technologies : []),
    ...(Array.isArray(raw.preferred_technologies) ? raw.preferred_technologies : []),
  ].map(s => String(s).trim()).filter(Boolean);

  const deduped = [...new Map(skills.map(s => [s.toLowerCase(), s])).values()];

  return {
    org_id: orgId,
    source_site: 'jsearch',
    external_id: raw.job_id ? String(raw.job_id) : null,
    title: raw.job_title || null,
    company_name: raw.employer_name || null,
    company_url: raw.employer_website || null,
    location: {
      raw: locationRaw,
      city: raw.job_city || null,
      state: raw.job_state || null,
      country: raw.job_country || null,
      is_remote: isRemote,
    },
    salary: {
      min: raw.job_min_salary ?? null,
      max: raw.job_max_salary ?? null,
      currency: raw.job_salary_currency || null,
      interval: raw.job_salary_period || null,
      source: 'jsearch',
    },
    job_type: normalizeJobType(raw.job_employment_type),
    description: raw.job_description || null,
    posted_at: postedAt,
    url: raw.job_apply_link || raw.job_google_link || null,
    skills: deduped,
    scraped_at: new Date(),
    raw,
  };
}

async function upsertJob(coll, job, orgId, now) {
  const query = job.external_id
    ? { org_id: orgId, source_site: job.source_site, external_id: job.external_id }
    : { org_id: orgId, source_site: job.source_site, title: job.title, company_name: job.company_name, url: job.url };

  const existing = await coll.findOne(query);

  if (existing) {
    await coll.updateOne({ _id: existing._id }, { $set: { ...job, updated_at: now } });
    return { job: { ...job, id: existing._id.toString() }, inserted: false };
  }

  const result = await coll.insertOne({ ...job, created_at: now, updated_at: now });
  return { job: { ...job, id: result.insertedId.toString() }, inserted: true };
}

export async function listScrapedJobs({ orgId = null, limit = 50, skip = 0, keyword, location, jobType, site, skills, fetchAll = false, datePosted = null }) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');
  const query = buildQuery({ orgId, keyword, location, jobType, site, skills });

  if (datePosted) {
    const now = new Date();
    const dateMap = {
      today: 1,
      '3days': 3,
      week: 7,
      month: 30,
    };
    const days = dateMap[datePosted];
    if (days) {
      const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
      query.scraped_at = { $gte: from };
    }
  }

  console.log(`[Jobs] listScrapedJobs query=${JSON.stringify(query)} fetchAll=${fetchAll} limit=${limit} skip=${skip}`);

  const total = await coll.countDocuments(query);
  console.log(`[Jobs] matched total=${total}`);

  let cursor = coll.find(query).sort({ scraped_at: -1 });
  if (!fetchAll) cursor = cursor.skip(skip).limit(limit);

  const docs = await cursor.toArray();
  return { total, jobs: docs.map(docToJob) };
}

export async function getPublicFilterCounts({ keyword, location, jobType, site, skills, datePosted = null }) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');
  const query = buildQuery({ orgId: null, keyword, location, jobType, site, skills });

  if (datePosted) {
    const dateMap = { today: 1, '3days': 3, week: 7, month: 30 };
    const days = dateMap[datePosted];
    if (days) query.scraped_at = { $gte: new Date(Date.now() - days * 24 * 60 * 60 * 1000) };
  }

  const [total, siteAgg, jobTypeAgg, skillsAgg] = await Promise.all([
    coll.countDocuments(query),
    coll.aggregate([{ $match: query }, { $group: { _id: '$source_site', count: { $sum: 1 } } }]).toArray(),
    coll.aggregate([{ $match: query }, { $group: { _id: '$job_type', count: { $sum: 1 } } }]).toArray(),
    coll.aggregate([
      { $match: query },
      { $unwind: '$skills' },
      { $group: { _id: '$skills', count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      { $limit: 50 },
    ]).toArray(),
  ]);

  return {
    total,
    by_site: Object.fromEntries(siteAgg.filter(r => r._id).map(r => [r._id, r.count])),
    by_job_type: Object.fromEntries(jobTypeAgg.filter(r => r._id).map(r => [r._id, r.count])),
    by_skills: Object.fromEntries(skillsAgg.filter(r => r._id).map(r => [r._id, r.count])),
  };
}

export async function getFetchStatus(orgId, sites) {
  const db = getDB();
  const now = new Date();

  return Promise.all(sites.map(async (site) => {
    const meta = site === 'indeed'
      ? await db.collection('site_fetch_meta').findOne({ org_id: orgId, site }, { sort: { last_fetched_at: -1 } })
      : await db.collection('site_fetch_meta').findOne({ org_id: orgId, site });

    if (!meta) return { site, last_fetched_at: null, next_allowed_at: null, can_fetch: true, hours_old: null };

    const last = meta.last_fetched_at;
    const nextAllowed = new Date(last.getTime() + COOLDOWN_MS);
    const canFetch = now >= nextAllowed;
    const hoursOld = canFetch ? Math.max(Math.floor((now - last) / 3600000), 1) : null;

    return { site, last_fetched_at: last, next_allowed_at: nextAllowed, can_fetch: canFetch, hours_old: hoursOld };
  }));
}

export async function getJobCounts({ orgId, keyword, location, isRemote, datePosted }) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');

  const baseQuery = { org_id: orgId };
  if (keyword) baseQuery.$or = [
    { title: { $regex: flexibleRegex(keyword), $options: 'i' } },
    { company_name: { $regex: flexibleRegex(keyword), $options: 'i' } },
  ];
  if (location) baseQuery['location.raw'] = { $regex: flexibleRegex(location), $options: 'i' };
  if (isRemote !== undefined) baseQuery['location.is_remote'] = isRemote === 'true';

  const allSites = ['google', 'glassdoor', 'zip_recruiter', 'indeed', 'jsearch'];
  const jobTypes = ['fulltime', 'contract', 'c2c', 'w2', 'c2h', 'contract_to_hire', 'parttime', 'internship'];

  const [allCount, ...siteCounts] = await Promise.all([
    coll.countDocuments(baseQuery),
    ...allSites.map(s => coll.countDocuments({ ...baseQuery, source_site: s })),
  ]);

  const siteJobTypeCounts = await Promise.all(
    allSites.flatMap(s => jobTypes.map(jt =>
      coll.countDocuments({ ...baseQuery, source_site: s, job_type: { $regex: jt, $options: 'i' } })
    ))
  );

  const sites = Object.fromEntries(allSites.map((s, i) => [s, siteCounts[i]]));
  const siteJobTypes = {};
  let idx = 0;
  for (const s of allSites) {
    siteJobTypes[s] = {};
    for (const jt of jobTypes) {
      siteJobTypes[s][jt] = siteJobTypeCounts[idx++];
    }
  }

  return { all: allCount, sites, siteJobTypes };
}

export async function searchAndStoreJsearchJobs({ keywords, location, country = 'us', language = null, numPages = 1, datePosted = 'all', workFromHome = false, employmentTypes = null, jobRequirements = null, radius = null, excludeJobPublishers = null, useCursor = false, cursor = null }, orgId) {
  const db = getDB();
  const coll = db.collection('scraped_jobs');
  const now = new Date();

  const query = `${keywords} jobs in ${location}`.trim();
  const lang = language || (country.toLowerCase() === 'us' ? 'en' : null);

  let rawJobs = [];
  let nextCursor = null;

  if (useCursor) {
    const result = await jsearchSearchV2({ query, numPages, cursor, country, language: lang, datePosted, workFromHome, employmentTypes, jobRequirements, radius, excludeJobPublishers });
    rawJobs = result.jobs;
    nextCursor = result.nextCursor;
  } else {
    rawJobs = await jsearchSearch({ query, numPages, country, language: lang, datePosted, workFromHome, employmentTypes, jobRequirements, radius, excludeJobPublishers });
  }

  let newCount = 0;
  const storedJobs = [];

  for (const raw of rawJobs) {
    const job = jsearchRawToJob(raw, orgId);
    const { job: saved, inserted } = await upsertJob(coll, job, orgId, now);
    if (inserted) newCount++;
    storedJobs.push(saved);
  }

  await db.collection('site_fetch_meta').updateOne(
    { org_id: orgId, site: 'jsearch' },
    { $set: { last_fetched_at: now, last_keywords: keywords, last_location: location, ...(nextCursor && { last_cursor: nextCursor }) } },
    { upsert: true }
  );

  return {
    fetched_count: rawJobs.length,
    stored_count: storedJobs.length,
    new_count: newCount,
    updated_count: storedJobs.length - newCount,
    next_cursor: nextCursor,
    jobs: storedJobs,
  };
}
