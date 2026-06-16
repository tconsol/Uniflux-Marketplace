import { Router } from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import {
  listScrapedJobs,
  getPublicFilterCounts,
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

// Public — no auth
router.get('/public/counts', async (req, res) => {
  try {
    const { keyword, location, job_type, site, skills, date_posted } = req.query;
    const result = await getPublicFilterCounts({ keyword, location, jobType: job_type, site, skills, datePosted: date_posted });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.get('/public', async (req, res) => {
  try {
    const { limit = 1000, skip = 0, keyword, location, job_type, site, skills, fetch_all, date_posted } = req.query;
    const result = await listScrapedJobs({
      orgId: null,
      limit: Math.min(parseInt(limit) || 1000, 1000),
      skip: parseInt(skip) || 0,
      keyword,
      location,
      jobType: job_type,
      site,
      skills,
      fetchAll: fetch_all === 'true',
      datePosted: date_posted,
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

// Auth required below
router.get('/', authenticate, async (req, res) => {
  try {
    const { limit = 50, skip = 0, keyword, location, job_type, site, skills, fetch_all } = req.query;
    const result = await listScrapedJobs({
      orgId: req.currentUser.orgId,
      limit: parseInt(limit),
      skip: parseInt(skip),
      keyword,
      location,
      jobType: job_type,
      site,
      skills,
      fetchAll: fetch_all === 'true',
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

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
    const result = await jsearchJobDetails({ jobId: job_id, country, language });
    res.json({ data: result });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/jsearch/estimated-salary', authenticate, async (req, res) => {
  try {
    const { job_title, location, location_type = 'ANY', years_of_experience = 'ALL' } = req.query;
    if (!job_title || !location) return res.status(400).json({ detail: 'job_title and location required' });
    const result = await jsearchEstimatedSalary({ jobTitle: job_title, location, locationType: location_type, yearsOfExperience: years_of_experience });
    res.json({ data: result });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/jsearch/company-salary', authenticate, async (req, res) => {
  try {
    const { company, job_title, location, location_type = 'ANY', years_of_experience = 'ALL' } = req.query;
    if (!company || !job_title) return res.status(400).json({ detail: 'company and job_title required' });
    const result = await jsearchCompanySalary({ company, jobTitle: job_title, location, locationType: location_type, yearsOfExperience: years_of_experience });
    res.json({ data: result });
  } catch (err) {
    res.status(502).json({ detail: `JSearch error: ${err.message}` });
  }
});

router.get('/fetch-status', authenticate, async (req, res) => {
  try {
    const sites = (req.query.sites || 'indeed,linkedin,glassdoor,zip_recruiter,google,jsearch')
      .split(',').map(s => s.trim()).filter(Boolean);
    const result = await getFetchStatus(req.currentUser.orgId, sites);
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.get('/counts', authenticate, async (req, res) => {
  try {
    const { keyword, location, is_remote, date_posted } = req.query;
    const result = await getJobCounts({
      orgId: req.currentUser.orgId,
      keyword,
      location,
      isRemote: is_remote,
      datePosted: date_posted,
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.get('/jsearch/scheduler/status', authenticate, async (req, res) => {
  try {
    const result = await getJsearchSchedulerStatusForOrg(req.currentUser.orgId);
    res.json(result);
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.post('/jsearch/scheduler/start', authenticate, async (req, res) => {
  try {
    const result = await startJsearchSchedulerForOrg(req.currentUser.orgId, req.body);
    res.json(result);
  } catch (err) {
    res.status(502).json({ detail: `Scheduler start error: ${err.message}` });
  }
});

router.post('/jsearch/scheduler/stop', authenticate, async (req, res) => {
  try {
    const result = await stopJsearchSchedulerForOrg(req.currentUser.orgId);
    res.json(result);
  } catch (err) {
    res.status(502).json({ detail: `Scheduler stop error: ${err.message}` });
  }
});

export default router;
