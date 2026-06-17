import { Router } from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import {
  getPublicJobs,
  getPublicJobsCount,
  getFetchStatus,
  getJobCounts,
  searchAndStoreJsearchJobs,
} from '../services/jobsService.js';
import {
  startJsearchSchedulerForOrg,
  stopJsearchSchedulerForOrg,
  getJsearchSchedulerStatusForOrg,
} from '../services/jsearchSchedulerService.js';
import {
  jsearchJobDetails,
  jsearchEstimatedSalary,
  jsearchCompanySalary,
} from '../services/jsearchService.js';

const router = Router();

// ─── PUBLIC (no auth) ────────────────────────────────────────────────────────

// GET paginated jobs — 200 per page, cursor-based (no duplicates)
// Filters: keyword, location, job_type, site, skills
// Pagination: pass next_cursor from previous response as cursor param
router.get('/public', async (req, res) => {
  try {
    const { keyword, location, job_type, site, skills, page = 1 } = req.query;
    const result = await getPublicJobs({
      keyword,
      location,
      jobType: job_type,
      site,
      skills,
      page: parseInt(page) || 1,
      limit: 200,
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

// GET total count + breakdown by site and job_type
router.get('/public/counts', async (req, res) => {
  try {
    const { keyword, location, job_type, site, skills } = req.query;
    const result = await getPublicJobsCount({ keyword, location, jobType: job_type, site, skills });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

// ─── AUTH REQUIRED ────────────────────────────────────────────────────────────

router.post('/jsearch', authenticate, async (req, res) => {
  try {
    const result = await searchAndStoreJsearchJobs({
      keywords: req.body.keywords,
      location: req.body.location,
      country: req.body.country || 'us',
      language: req.body.language || null,
      numPages: req.body.num_pages || 1,
      datePosted: req.body.date_posted || 'all',
      workFromHome: req.body.work_from_home || false,
      employmentTypes: req.body.employment_types || null,
      jobRequirements: req.body.job_requirements || null,
      radius: req.body.radius || null,
      excludeJobPublishers: req.body.exclude_job_publishers || null,
      useCursor: req.body.use_cursor || false,
      cursor: req.body.cursor || null,
    }, req.currentUser.orgId);
    res.json(result);
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/jsearch/job-details', authenticate, async (req, res) => {
  try {
    const { job_id, country = 'us', language } = req.query;
    if (!job_id) return res.status(400).json({ detail: 'job_id required' });
    res.json({ data: await jsearchJobDetails({ jobId: job_id, country, language }) });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/jsearch/estimated-salary', authenticate, async (req, res) => {
  try {
    const { job_title, location, location_type = 'ANY', years_of_experience = 'ALL' } = req.query;
    if (!job_title || !location) return res.status(400).json({ detail: 'job_title and location required' });
    res.json({ data: await jsearchEstimatedSalary({ jobTitle: job_title, location, locationType: location_type, yearsOfExperience: years_of_experience }) });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/jsearch/company-salary', authenticate, async (req, res) => {
  try {
    const { company, job_title, location, location_type = 'ANY', years_of_experience = 'ALL' } = req.query;
    if (!company || !job_title) return res.status(400).json({ detail: 'company and job_title required' });
    res.json({ data: await jsearchCompanySalary({ company, jobTitle: job_title, location, locationType: location_type, yearsOfExperience: years_of_experience }) });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/fetch-status', authenticate, async (req, res) => {
  try {
    const sites = (req.query.sites || 'indeed,linkedin,glassdoor,zip_recruiter,google,jsearch')
      .split(',').map(s => s.trim()).filter(Boolean);
    res.json(await getFetchStatus(req.currentUser.orgId, sites));
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.get('/counts', authenticate, async (req, res) => {
  try {
    const { keyword, location, is_remote, date_posted } = req.query;
    res.json(await getJobCounts({ orgId: req.currentUser.orgId, keyword, location, isRemote: is_remote, datePosted: date_posted }));
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.get('/jsearch/scheduler/status', authenticate, async (req, res) => {
  try {
    res.json(await getJsearchSchedulerStatusForOrg(req.currentUser.orgId));
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.post('/jsearch/scheduler/start', authenticate, async (req, res) => {
  try {
    res.json(await startJsearchSchedulerForOrg(req.currentUser.orgId, req.body));
  } catch (err) {
    res.status(502).json({ detail: `Scheduler start error: ${err.message}` });
  }
});

router.post('/jsearch/scheduler/stop', authenticate, async (req, res) => {
  try {
    res.json(await stopJsearchSchedulerForOrg(req.currentUser.orgId));
  } catch (err) {
    res.status(502).json({ detail: `Scheduler stop error: ${err.message}` });
  }
});

export default router;
