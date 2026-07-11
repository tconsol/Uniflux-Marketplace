# Global Marketplace Job Pool + Auto-Active Indeed Scheduler

Date: 2026-07-11
Status: Approved (design)
Service: `Uniflux-Marketplace` (FastAPI, Cloud Run, asia-south1)

## Problem

The marketplace is currently **org-scoped**: scraped jobs are stored with the
caller's `org_id`, dedupe keys on `org_id`, and both read paths (`/jobs` list,
`/counts`) filter by the caller's `org_id`. All 102,936 existing jobs are tagged
`ORG_5F5EA795`, so any other subscribed org sees an empty board.

The intended model is: **one common job pool for the whole platform**;
subscription only gates *who can view* (enforced at the api-gateway, already
deployed). Additionally, the indeed scheduler is per-org, in-memory APScheduler,
and is **never re-registered on startup**, so after any Cloud Run recycle it
silently stops (last real tick 2026-07-01). It must instead be a single global
scheduler that is **active by default on every redeploy**.

## Scope

- IN: indeed scheduler → global + auto-active; global job pool (storage, dedupe,
  reads); one-time migration of existing jobs; required Cloud Run deploy flag.
- OUT (follow-up): jsearch, dice, monster, glassdoor schedulers (same pattern);
  moving scheduling to Cloud Scheduler.

## Design

### 1. Global pool sentinel
Add `GLOBAL_ORG_ID = "GLOBAL"` (module-level constant, e.g. `app/constants.py`
or top of `jobs_service.py`). Every marketplace job write uses it — the
scheduler tick and the manual `/search` + `/jsearch` endpoints. `ScrapedJob.org_id`
field is retained (no schema break); it simply always holds `"GLOBAL"`.

### 2. Global dedupe
`_job_identity_query(job)` drops `org_id`; identity =
`source_site + external_id`, fallback `source_site + title + company_name + url`.
Single pool ⇒ no cross-org duplication. `site_fetch_meta` cooldown records key on
`GLOBAL` + site (+ keywords/location for indeed).

### 3. Reads ignore org
- `/jobs` list (`routers/jobs.py::get_scraped_jobs`) → `list_scraped_jobs(org_id=None, ...)`.
- `/counts` (`routers/jobs.py::job_counts` → `get_job_counts`) → base query `{}`
  (remove `org_id`). Signature keeps `org_id` optional/ignored or is dropped.
- Auth: endpoints still `Depends(get_current_user)` (valid token required); the
  caller's org is no longer used to filter. Subscription gating remains at the
  gateway (`ServiceAccessFilter.validate("MARKET_PLACE")`, deployed).

### 4. Global auto-active indeed scheduler
- Single job id `indeed_auto_pull:GLOBAL`; state doc in `indeed_scheduler_meta`
  keyed `{"org_id": "GLOBAL"}` (reuse collection; the key is just the sentinel).
- `init_indeed_scheduler()` (called from `main.py` lifespan on startup):
  1. `scheduler.start()`
  2. Register/replace the global job with the default config
     (`location="United States"`, `interval_minutes=30`, the 14 default keywords),
     `enabled=true`, `replace_existing=True`, `max_instances=1`, `coalesce=True`.
  3. Persist the state doc (preserve `current_keyword_index` if present so rotation
     continues across restarts).
- Runs on **every** startup regardless of prior DB state ⇒ active by default on
  each redeploy.
- `_run_indeed_tick` takes no org (or `GLOBAL`); rotates keywords via
  `current_keyword_index` in the GLOBAL state doc; calls `search_and_store_jobs`
  writing to `GLOBAL`.
- Endpoints `/indeed/scheduler/{status,start,stop}` operate on the global job
  (no per-org state). They keep `get_current_user` (subscription-gated at gateway).

### 5. One-time idempotent migration
On startup, before/after scheduler init:
`scraped_jobs.update_many({"org_id": {"$ne": "GLOBAL"}}, {"$set": {"org_id": "GLOBAL"}})`.
Guarded by the `$ne` filter ⇒ cheap no-op after first boot. Folds the existing
102,936 jobs into the pool. No duplicate collisions (all currently one org).

### 6. Cloud Run persistence (REQUIRED deploy flag)
In-process APScheduler is lost when the instance scales to zero, and ticks can't
fire while asleep. The marketplace Cloud Run service **must** deploy with
`--min-instances=1` so one warm instance always runs the scheduler. Documented as
part of the deploy step. Long-term robust alternative (Cloud Scheduler → an
internal tick endpoint) is a separate follow-up.

## Testing

Local (dev Mongo, `.env`):
- On startup, `GET /api/v1/marketplace/indeed/scheduler/status` → `enabled:true`,
  `running:true`, `next_run_at` set.
- `GET /counts` and `GET /jobs/` return the whole pool (no org filter).
- `POST /jobs/search` writes with `org_id="GLOBAL"`.
- Trigger one tick (short interval override in a test) → jobs stored under GLOBAL.

Prod (after deploy WITH `--min-instances=1`):
- Scheduler `running:true`, `next_run_at` set, `last_run_at` advances.
- A second subscribed org's token → `/counts` returns the same totals (proves
  common pool).
- Migration folded existing jobs (total unchanged/served to all orgs).

## Risks / notes
- Without `--min-instances=1` the scheduler still won't tick reliably — the flag
  is not optional for this design.
- Interval 30 min through the configured proxy keeps scraping load sustainable
  (~48 keyword-pulls/day) vs the old 2 min (~720/day, ban/cost risk).
- Manual `/search` now contributes to the shared pool for all orgs (intended).
