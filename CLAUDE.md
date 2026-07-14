# Uniflux-Marketplace — CLAUDE.md

## Tech Stack
### Python Service (primary)
- **Language:** Python 3.11
- **Framework:** FastAPI (async, via Uvicorn)
- **Database:** MongoDB via Motor (async driver)
- **Job Scraping:** `python-jobspy` (Indeed, Glassdoor, Google, LinkedIn, ZipRecruiter)
- **Job Search API:** OpenWebNinja/JSearch API
- **Scheduling:** APScheduler (AsyncIOScheduler)
- **Auth:** JWT (python-jose, HS256)
- **Service Discovery:** Netflix Eureka via `py_eureka_client`
- **HTTP Client:** httpx (async)
- **Proxy:** SOCKS5 proxy for JobSpy scraping
- **Container:** Docker (python:3.11-slim)
- **Port:** 8085

### Node.js Service (secondary)
- **Runtime:** Node 20 (alpine)
- **Framework:** Express.js
- **Database:** MongoDB via native `mongodb` driver
- **Scheduling:** node-cron
- **HTTP Client:** axios
- **Auth:** jsonwebtoken (HS256)
- **Container:** Docker (node:20-alpine)
- **Port:** 3085 (default Express)

## Architecture & Role
**Job aggregation marketplace** — scrapes jobs from multiple sources (Indeed, Glassdoor, Google, LinkedIn, ZipRecruiter via JobSpy; JSearch API for web-wide listings) and exposes them via REST API. Has **two parallel implementations** (Python+Node) hitting the same MongoDB. Supports per-org job isolation, cooldown-based fetching, scheduled auto-scraping, and public endpoints for frontend.

## Directory Structure
```
app/ (Python FastAPI)
├── main.py                       — FastAPI entry, lifespan, scheduler init
├── config.py                     — Pydantic Settings
├── database.py                   — Motor async MongoDB
├── eureka_client.py              — Eureka registration
├── middleware/auth_middleware.py  — JWT auth, CurrentUser, role guards
├── models/scraped_job.py         — All Pydantic models (requests, responses)
├── routers/
│   ├── jobs.py                   — Job search, fetch, scheduler status
│   └── indeed_scheduler.py       — Indeed scheduler control
└── services/
    ├── jobs_service.py           — Core business logic (683 lines)
    ├── jobspy_service.py         — JobSpy library wrapper
    ├── jsearch_service.py        — OpenWebNinja API client
    ├── jsearch_scheduler_service.py  — APScheduler for JSearch
    └── indeed_scheduler_service.py   — APScheduler for Indeed

node-server/ (Node.js Express)
├── Dockerfile
├── package.json
├── API_INTEGRATION.md
└── src/
    ├── app.js                    — Express entry, scheduler restore
    ├── database.js               — MongoDB native driver + indexes
    ├── config/settings.js        — Config from .env
    ├── middleware/authMiddleware.js — JWT auth
    ├── routes/
    │   ├── jobs.js               — Jobs + JSearch scheduler routes
    │   └── indeedScheduler.js    — Indeed scheduler routes
    └── services/
        ├── jobsService.js        — Core business logic
        ├── jsearchService.js     — JSearch API client (axios)
        ├── jsearchSchedulerService.js — node-cron for JSearch
        └── indeedSchedulerService.js  — node-cron for Indeed (stub, needs Python)
```

## All API Endpoints

### Python FastAPI (port 8085)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | Health check |
| GET | `/api/v1/marketplace/jobs/public` | Public | List scraped jobs (filters: keyword, location, job_type, site, skills) |
| GET | `/api/v1/marketplace/jobs/public/counts` | Public | Count breakdown by site, job_type, skills |
| POST | `/api/v1/marketplace/jobs/search` | JWT | Search & store via JobSpy |
| POST | `/api/v1/marketplace/jobs/jsearch` | JWT | Search & store via JSearch API |
| GET | `/api/v1/marketplace/jobs/fetch-status` | JWT | Per-site cooldown status |
| GET | `/api/v1/marketplace/jobs/counts` | JWT | Job counts with filtering |
| GET | `/api/v1/marketplace/jobs/` | JWT | List stored jobs (org-scoped). Filters: `keyword`, `location`, `job_type`, `site`, `skills`, `is_remote` (fixed 2026-07-14, was accepted by the frontend but silently dropped server-side — see below), `date_posted` (same fix, days-back window, permissive on missing `posted_at` to match frontend `matchesDatePosted`) |
| GET | `/api/v1/marketplace/jobs/jsearch/scheduler/status` | JWT | JSearch scheduler status |
| POST | `/api/v1/marketplace/jobs/jsearch/scheduler/start` | JWT | Start JSearch scheduler |
| POST | `/api/v1/marketplace/jobs/jsearch/scheduler/stop` | JWT | Stop JSearch scheduler |
| GET | `/api/v1/marketplace/indeed/scheduler/status` | JWT | Indeed scheduler status |
| POST | `/api/v1/marketplace/indeed/scheduler/start` | JWT | Start Indeed scheduler |
| POST | `/api/v1/marketplace/indeed/scheduler/stop` | JWT | Stop Indeed scheduler |

### Node.js Express (port 3085) — REMOVED (see commit c95f335 "remove node-server, port its 3 unique endpoints into the Python service"). This section is stale; the repo is Python-only now.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | Health check |
| GET | `/api/v1/marketplace/jobs/public` | Public | Paginated public jobs (offset-based) |
| GET | `/api/v1/marketplace/jobs/public/counts` | Public | Public counts |
| POST | `/api/v1/marketplace/jobs/jsearch` | JWT | JSearch + store |
| GET | `/api/v1/marketplace/jobs/jsearch/job-details` | JWT | JSearch job detail proxy |
| GET | `/api/v1/marketplace/jobs/jsearch/estimated-salary` | JWT | Salary estimation proxy |
| GET | `/api/v1/marketplace/jobs/jsearch/company-salary` | JWT | Company salary proxy |
| GET | `/api/v1/marketplace/jobs/fetch-status` | JWT | Cooldown status |
| GET | `/api/v1/marketplace/jobs/counts` | JWT | Job type counts |
| GET | `/api/v1/marketplace/jobs/jsearch/scheduler/status` | JWT | Scheduler status |
| POST | `/api/v1/marketplace/jobs/jsearch/scheduler/start` | JWT | Start scheduler |
| POST | `/api/v1/marketplace/jobs/jsearch/scheduler/stop` | JWT | Stop scheduler |
| GET | `/api/v1/marketplace/indeed/scheduler/status` | JWT | Indeed status |
| POST | `/api/v1/marketplace/indeed/scheduler/start` | JWT | Start Indeed |
| POST | `/api/v1/marketplace/indeed/scheduler/stop` | JWT | Stop Indeed |

## Data Model — `scraped_job` (Collection: `scraped_jobs`)

| Field | Type | Notes |
|-------|------|-------|
| `org_id` | String | Org scope |
| `source_site` | String | indeed/glassdoor/google/linkedin/zip_recruiter/jsearch |
| `external_id` | String (optional) | Source job ID |
| `title` | String | Job title |
| `company_name` | String (optional) | Company |
| `company_url` | String (optional) | Company website |
| `location` | Embedded | `{raw, city, state, country, is_remote}` |
| `salary` | Embedded | `{min, max, currency, interval, source}` |
| `job_type` | String (optional) | Normalized (fulltime, parttime, contract, etc.) |
| `description` | String (optional) | Job description |
| `posted_at` | datetime (optional) | Posted date |
| `url` | String (optional) | Apply URL |
| `skills` | List[String] | Extracted skills |
| `scraped_at` | datetime | When scraped |
| `created_at`, `updated_at` | datetime | Timestamps |

### MongoDB Indexes
- `_id: 1` — default
- `source_site: 1, _id: 1` — site queries
- `job_type: 1, _id: 1` — type queries
- `location.raw: 1, _id: 1` — location queries
- `skills: 1, _id: 1` — skills queries
- `title: 1, _id: 1` — title search
- `org_id: 1, _id: 1` — org scope
- `scraped_at: -1` — recency sort

## Auth Mechanism
- **JWT Bearer token** (HS256, shared secret)
- Expected claims: `userId` (or `sub`), `name`, `orgId` (required), `role`
- Roles: EMPLOYEE, MANAGER, ADMIN, ORG_ADMIN
- Guards: `require_manager()`, `require_admin()`
- Public endpoints: `/public`, `/public/counts`, `/health`

## Sidebar Filter Fixes (2026-07-14, don't regress)
- **`is_remote`/`date_posted` were accepted by the frontend (`Uniflux-Market-Place-UI`'s `useJobs.ts`) but the `GET /jobs/` route (`routers/jobs.py`) and `list_scraped_jobs()` (`services/jobs_service.py`) didn't have those params at all — silently ignored. Real no-op filters on the Indeed/LinkedIn/JSearch tabs specifically (the frontend's `SiteJobsPage.tsx` only client-refilters for the *custom-site* tabs — Glassdoor/Dice/Monster — not for jobs coming from this service). Both params are now threaded through end-to-end.
- **`_flexible_regex()` job_type mismatch**: frontend sends compact, separator-free tokens (`"fulltime"`, `"contracttohire"`) but the old implementation only inserted optional separators *between words the input already had separators for* — a compact token has none, so it degenerated into a literal substring search that never matched `"Full-Time"` in Mongo. Fixed by stripping separators from the input first, then inserting an optional-separator pattern between every remaining character, so matching is symmetric regardless of which side has the punctuation. Covers `job_type`, `keyword`, `location`, and `skills` filters (all route through the same helper).

## Scraping Engines

### 1. JobSpy (`python-jobspy` v1.1.82)
- Wraps `jobspy.scrape_jobs()` 
- Sites: indeed, glassdoor, google, linkedin, zip_recruiter
- Proxy support via `PROXY_URL` env var (SOCKS5 proxy at `198.23.239.134:6540`)
- Returns pandas DataFrame → converted to ScrapedJob documents
- Cooldown: 15-minute minimum between scrapes per site per org (stored in `site_fetch_meta` collection)

### 2. OpenWebNinja / JSearch API
- REST API at `https://api.openwebninja.com`
- Endpoints: `/search` (full-text), `/search-v2` (cursor pagination), `/job-details`, `/estimated-salary`, `/company-job-salary`
- Auth via `OPENWEBNINJA_API_KEY` in `X-API-Key` header
- Cursor-based pagination support for deep fetching

## Scheduler System
### JSearch Scheduler (APScheduler/node-cron)
- Iterates through all configured keywords
- Calls `search_and_store_jsearch_jobs()` per keyword
- State persisted in MongoDB `jsearch_scheduler_meta` collection

### Indeed Scheduler (APScheduler/node-cron)
- Rotates through keywords one at a time (round-robin)
- Tracks `current_keyword_index` in MongoDB
- State in `indeed_scheduler_meta` collection

## Business Logic Flow
```
Request → Router → Service Layer
  ├─ JobSpy: search_and_store_jobs()
  │   → check cooldown → jobspy_search() → pandas DataFrame
  │   → _row_to_scraped_job() → _upsert_job() into MongoDB
  │
  ├─ JSearch: search_and_store_jsearch_jobs()
  │   → jsearch_search() or jsearch_search_v2() (cursor)
  │   → _jsearch_job_to_scraped() → _upsert_job()
  │
  └─ Scheduler: APScheduler/node-cron ticks
      → rotates through keywords → calls search functions
      → persists state in scheduler_meta collections
```

## External Communication
- **MongoDB Atlas:** `mongodb+srv://Uniflux_development@uniflux-development.1ervtku.mongodb.net/market-place`
- **OpenWebNinja/JSearch:** REST API via httpx/axios
- **JobSpy:** Python library with optional proxy
- **Eureka:** Registers as `marketplace` at `http://localhost:8761/eureka/`
- **API Gateway:** Sits behind Spring Cloud Gateway

## CORS
- Frontend URLs: `http://localhost:5173` (from .env)

## Dev Setup
```bash
# Python service
cd app
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8085

# Node.js service  
cd node-server
npm install
node src/app.js

# Docker
docker build -t uniflux-marketplace .
docker run -p 8085:8085 uniflux-marketplace
```