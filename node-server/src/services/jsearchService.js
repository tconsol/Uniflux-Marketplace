import axios from 'axios';
import { settings } from '../config/settings.js';

const JSEARCH_BASE_URL = 'https://api.openwebninja.com/jsearch';

function getHeaders() {
  const key = settings.OPENWEBNINJA_API_KEY;
  if (!key) throw new Error('OPENWEBNINJA_API_KEY is not set');
  return { 'x-api-key': key };
}

function cleanParams(params) {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
  );
}

export async function jsearchSearch({
  query,
  numPages = 1,
  page = 1,
  country = 'us',
  language = null,
  datePosted = 'all',
  workFromHome = false,
  employmentTypes = null,
  jobRequirements = null,
  radius = null,
  excludeJobPublishers = null,
}) {
  const params = cleanParams({
    query,
    page,
    num_pages: numPages,
    country,
    language,
    date_posted: datePosted,
    work_from_home: String(workFromHome),
    employment_types: employmentTypes,
    job_requirements: jobRequirements,
    radius,
    exclude_job_publishers: excludeJobPublishers,
  });

  const resp = await axios.get(`${JSEARCH_BASE_URL}/search`, {
    headers: getHeaders(),
    params,
    timeout: 30000,
  });

  return resp.data?.data || [];
}

export async function jsearchSearchV2({
  query,
  numPages = 1,
  cursor = null,
  country = 'us',
  language = null,
  datePosted = 'all',
  workFromHome = false,
  employmentTypes = null,
  jobRequirements = null,
  radius = null,
  excludeJobPublishers = null,
}) {
  const params = cleanParams({
    query,
    num_pages: numPages,
    cursor,
    country,
    language,
    date_posted: datePosted,
    work_from_home: String(workFromHome),
    employment_types: employmentTypes,
    job_requirements: jobRequirements,
    radius,
    exclude_job_publishers: excludeJobPublishers,
  });

  const resp = await axios.get(`${JSEARCH_BASE_URL}/search-v2`, {
    headers: getHeaders(),
    params,
    timeout: 30000,
  });

  const dataBlock = resp.data?.data || {};
  return {
    jobs: dataBlock.jobs || [],
    nextCursor: dataBlock.cursor || null,
  };
}

export async function jsearchJobDetails({ jobId, country = 'us', language = null }) {
  const params = cleanParams({ job_id: jobId, country, language });
  const resp = await axios.get(`${JSEARCH_BASE_URL}/job-details`, {
    headers: getHeaders(),
    params,
    timeout: 30000,
  });
  const data = resp.data?.data || [];
  return data[0] || null;
}

export async function jsearchEstimatedSalary({
  jobTitle,
  location,
  locationType = 'ANY',
  yearsOfExperience = 'ALL',
}) {
  const params = cleanParams({
    job_title: jobTitle,
    location,
    location_type: locationType,
    years_of_experience: yearsOfExperience,
  });

  const resp = await axios.get(`${JSEARCH_BASE_URL}/estimated-salary`, {
    headers: getHeaders(),
    params,
    timeout: 30000,
  });

  return resp.data?.data || [];
}

export async function jsearchCompanySalary({
  company,
  jobTitle,
  location = null,
  locationType = 'ANY',
  yearsOfExperience = 'ALL',
}) {
  const params = cleanParams({
    company,
    job_title: jobTitle,
    location,
    location_type: locationType,
    years_of_experience: yearsOfExperience,
  });

  const resp = await axios.get(`${JSEARCH_BASE_URL}/company-job-salary`, {
    headers: getHeaders(),
    params,
    timeout: 30000,
  });

  return resp.data?.data || [];
}