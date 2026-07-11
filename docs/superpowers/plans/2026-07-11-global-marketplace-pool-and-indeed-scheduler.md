# Global Marketplace Pool + Auto-Active Indeed Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the marketplace a single global job pool (subscription gates viewing only, at the gateway) and turn the indeed scheduler into one global job that is active by default on every redeploy.

**Architecture:** All marketplace job writes use a `GLOBAL` sentinel org id; dedupe and both read paths (`/jobs`, `/counts`) stop filtering by org. A one-time idempotent startup migration folds existing jobs into the pool. The indeed scheduler registers a single global job at startup (always enabled) writing to the pool.

**Tech Stack:** FastAPI, Motor (async MongoDB), APScheduler (AsyncIOScheduler), pytest + pytest-asyncio (new, for pure-logic units), uvicorn + curl for runtime verification.

## Global Constraints

- Sentinel value is exactly `"GLOBAL"` (constant `GLOBAL_ORG_ID`).
- Global indeed scheduler config: `location="United States"`, `interval_minutes=30`, the 14 default keywords from `IndeedSchedulerConfig`, rotating one keyword per tick.
- Scope: indeed only. Do NOT touch jsearch/dice/monster/glassdoor schedulers.
- The marketplace Cloud Run service MUST be deployed with `--min-instances=1` (documented in Task 7); without it the in-process scheduler will not tick.
- Auth is unchanged: endpoints keep `Depends(get_current_user)`; the caller's org is simply no longer used for filtering. Subscription gating stays at the gateway (`ServiceAccessFilter.validate("MARKET_PLACE")`, already deployed).
- Dev DB for runtime verification comes from `.env` (`MONGODB_URI`, `market-place`). Run local server on port 8099.

---

### Task 1: GLOBAL_ORG_ID constant + pytest tooling

**Files:**
- Create: `app/constants.py`
- Modify: `requirements.txt`
- Test: `tests/test_constants.py`
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Produces: `app.constants.GLOBAL_ORG_ID: str == "GLOBAL"`

- [ ] **Step 1: Write the failing test**

`tests/test_constants.py`:
```python
from app.constants import GLOBAL_ORG_ID


def test_global_org_id_value():
    assert GLOBAL_ORG_ID == "GLOBAL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Uniflux/Uniflux_backend/Uniflux-Marketplace && python -m pytest tests/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.constants'` (and pytest may be missing → install in Step 3).

- [ ] **Step 3: Add tooling + implementation**

Append to `requirements.txt`:
```
pytest==8.3.4
pytest-asyncio==0.25.2
```
Install: `python -m pip install pytest==8.3.4 pytest-asyncio==0.25.2`

Create `app/constants.py`:
```python
# Shared marketplace constants.

# All marketplace job data lives in one global pool; the ScrapedJob.org_id field
# is retained for schema stability but always holds this sentinel. Subscription
# gating (who may VIEW the board) is enforced at the api-gateway, not here.
GLOBAL_ORG_ID = "GLOBAL"
```
Create empty `tests/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_constants.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/constants.py tests/__init__.py tests/test_constants.py requirements.txt
git commit -m "feat(marketplace): add GLOBAL_ORG_ID sentinel + pytest tooling"
```

---

### Task 2: Global dedupe identity

**Files:**
- Modify: `app/services/jobs_service.py` (`_job_identity_query` ~254-268, `_upsert_job` ~271-295)
- Test: `tests/test_dedupe_identity.py`

**Interfaces:**
- Consumes: `app.constants.GLOBAL_ORG_ID`
- Produces: `_job_identity_query(job: ScrapedJob) -> Dict[str, Any]` (no org_id param, org not in query); `_upsert_job(jobs_coll, job, now)` (org_id param removed).

- [ ] **Step 1: Write the failing test**

`tests/test_dedupe_identity.py`:
```python
from datetime import datetime
from app.services.jobs_service import _job_identity_query
from app.models.scraped_job import ScrapedJob


def _job(**kw):
    base = dict(org_id="GLOBAL", source_site="indeed", scraped_at=datetime.utcnow())
    base.update(kw)
    return ScrapedJob(**base)


def test_identity_uses_external_id_without_org():
    q = _job_identity_query(_job(external_id="abc123"))
    assert q == {"source_site": "indeed", "external_id": "abc123"}


def test_identity_fallback_without_org():
    q = _job_identity_query(_job(title="Dev", company_name="Acme", url="http://x"))
    assert "org_id" not in q
    assert q["source_site"] == "indeed"
    assert q["title"] == "Dev"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dedupe_identity.py -v`
Expected: FAIL — `_job_identity_query()` currently requires `(job, org_id)` and includes `org_id` → TypeError/assertion.

- [ ] **Step 3: Write minimal implementation**

In `app/services/jobs_service.py`, replace `_job_identity_query`:
```python
def _job_identity_query(job: ScrapedJob) -> Dict[str, Any]:
    if job.external_id:
        return {
            "source_site": job.source_site,
            "external_id": job.external_id,
        }

    return {
        "source_site": job.source_site,
        "title": job.title,
        "company_name": job.company_name,
        "url": job.url,
    }
```
Update `_upsert_job` signature + call site:
```python
async def _upsert_job(
    jobs_coll,
    job: ScrapedJob,
    now: datetime,
) -> Tuple[ScrapedJob, bool]:
    query = _job_identity_query(job)
    existing = await jobs_coll.find_one(query)
    ...
```
Update the two `_upsert_job(jobs_coll, job, org_id, now)` call sites (in `search_and_store_jobs` ~378 and `search_and_store_jsearch_jobs` ~443) to `_upsert_job(jobs_coll, job, now)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dedupe_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/jobs_service.py tests/test_dedupe_identity.py
git commit -m "feat(marketplace): global job dedupe identity (drop org_id)"
```

---

### Task 3: Force GLOBAL on all job writes

**Files:**
- Modify: `app/services/jobs_service.py` (`search_and_store_jobs` ~341, `search_and_store_jsearch_jobs` ~391)
- Modify: `app/routers/jobs.py` (`search_jobs` ~92, `search_jobs_jsearch` ~103)

**Interfaces:**
- Consumes: `app.constants.GLOBAL_ORG_ID`
- Produces: `search_and_store_jobs(payload) -> ScrapedJobListResponse` writes with org_id GLOBAL regardless of caller; `search_and_store_jsearch_jobs(payload) -> JSearchFetchResponse` likewise.

- [ ] **Step 1: Implementation**

Add import at top of `app/services/jobs_service.py`:
```python
from app.constants import GLOBAL_ORG_ID
```
Change `search_and_store_jobs` signature + first line so all internal `org_id` usage is the sentinel:
```python
async def search_and_store_jobs(payload: JobSearchRequest, org_id: str = GLOBAL_ORG_ID) -> ScrapedJobListResponse:
    org_id = GLOBAL_ORG_ID
    ...
```
Change `search_and_store_jsearch_jobs` the same way:
```python
async def search_and_store_jsearch_jobs(payload: JSearchRequest, org_id: str = GLOBAL_ORG_ID) -> JSearchFetchResponse:
    org_id = GLOBAL_ORG_ID
    ...
```
In `app/routers/jobs.py`, simplify the two search endpoints (keep auth dependency, drop passing org):
```python
    return await search_and_store_jobs(payload)
```
```python
    return await search_and_store_jsearch_jobs(payload)
```

- [ ] **Step 2: Runtime verification (dev Mongo)**

Start server:
```bash
cd D:/Uniflux/Uniflux_backend/Uniflux-Marketplace
python -m uvicorn app.main:app --host 127.0.0.1 --port 8099 &
```
Sign a local HS512 token (dev secret `uniflux-super-secret-key-must-be-32-chars-min`, any org):
```bash
python - <<'PY'
from jose import jwt
print(jwt.encode({"sub":"u","email":"t@t.com","role":"ORG_ADMIN","orgId":"ORG_ANY","type":"ACCESS"},
  "uniflux-super-secret-key-must-be-32-chars-min", algorithm="HS512"))
PY
```
POST a small search and confirm stored under GLOBAL:
```bash
TOK=<token>
curl -s -X POST "http://127.0.0.1:8099/api/v1/marketplace/jobs/search" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d '{"keywords":"software engineer","location":"United States","sites":["indeed"],"results_wanted":2}' | head -c 200
```
Then verify in Mongo the newest docs have `org_id="GLOBAL"`:
```bash
python - <<'PY'
import asyncio
from app.database import get_db
async def main():
    d = get_db()
    doc = await d.scraped_jobs.find_one(sort=[("created_at",-1)])
    print("newest org_id:", doc.get("org_id"))
asyncio.run(main())
PY
```
Expected: `newest org_id: GLOBAL`

- [ ] **Step 3: Commit**

```bash
git add app/services/jobs_service.py app/routers/jobs.py
git commit -m "feat(marketplace): all job writes go to the GLOBAL pool"
```

---

### Task 4: Global reads (drop org filter on /jobs + /counts)

**Files:**
- Modify: `app/services/jobs_service.py` (`get_job_counts` ~619-683)
- Modify: `app/routers/jobs.py` (`get_scraped_jobs` ~205, `job_counts` ~184)

**Interfaces:**
- Produces: `get_job_counts(keyword=None, location=None, is_remote=None, date_posted=None) -> Dict[str, Any]` (org_id removed; counts over the whole pool). `list_scraped_jobs(org_id=None, ...)` already supported — router passes `None`.

- [ ] **Step 1: Implementation**

In `app/services/jobs_service.py`, change `get_job_counts` signature + base query:
```python
async def get_job_counts(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    is_remote: Optional[str] = None,
    date_posted: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    jobs_coll = db.scraped_jobs

    base_query: Dict[str, Any] = {}
    ...
```
(Leave the rest of the function unchanged.)

In `app/routers/jobs.py` `get_scraped_jobs`, change the call to not filter by org:
```python
    return await list_scraped_jobs(
        org_id=None,
        limit=limit,
        skip=skip,
        keyword=keyword,
        location=location,
        job_type=job_type,
        site=site,
        skills=skills,
        fetch_all=fetch_all,
    )
```
In `app/routers/jobs.py` `job_counts`, drop the org arg:
```python
    return await get_job_counts(
        keyword=keyword,
        location=location,
        is_remote=is_remote,
        date_posted=date_posted,
    )
```

- [ ] **Step 2: Runtime verification (dev Mongo)**

With the server running (Task 3), using a token whose `orgId` is some org that has NO jobs of its own (e.g. `ORG_ANY`):
```bash
curl -s "http://127.0.0.1:8099/api/v1/marketplace/jobs/counts" -H "Authorization: Bearer $TOK" | head -c 120
curl -s "http://127.0.0.1:8099/api/v1/marketplace/jobs/?limit=1" -H "Authorization: Bearer $TOK" | head -c 120
```
Expected: `all`/`total` reflect the WHOLE collection (non-zero even though `ORG_ANY` never scraped) — proves the org filter is gone.

- [ ] **Step 3: Commit**

```bash
git add app/services/jobs_service.py app/routers/jobs.py
git commit -m "feat(marketplace): /jobs and /counts read the global pool (no org filter)"
```

---

### Task 5: Idempotent startup migration

**Files:**
- Modify: `app/services/jobs_service.py` (add `migrate_jobs_to_global`)
- Modify: `app/main.py` (call in lifespan)
- Test: `tests/test_migration_signature.py`

**Interfaces:**
- Produces: `async def migrate_jobs_to_global() -> int` (returns modified_count).

- [ ] **Step 1: Write the failing test**

`tests/test_migration_signature.py`:
```python
import inspect
from app.services.jobs_service import migrate_jobs_to_global


def test_migration_is_async_zero_arg():
    assert inspect.iscoroutinefunction(migrate_jobs_to_global)
    assert list(inspect.signature(migrate_jobs_to_global).parameters) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_migration_signature.py -v`
Expected: FAIL — `ImportError: cannot import name 'migrate_jobs_to_global'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/services/jobs_service.py`:
```python
async def migrate_jobs_to_global() -> int:
    """Fold any pre-existing org-scoped jobs into the single global pool.

    Idempotent: the $ne filter makes this a cheap no-op after the first run.
    """
    db = get_db()
    result = await db.scraped_jobs.update_many(
        {"org_id": {"$ne": GLOBAL_ORG_ID}},
        {"$set": {"org_id": GLOBAL_ORG_ID}},
    )
    if result.modified_count:
        logger.info("Migrated %d jobs to GLOBAL pool", result.modified_count)
    return result.modified_count
```
In `app/main.py` lifespan, call it before scheduler init:
```python
from app.services.jobs_service import migrate_jobs_to_global
...
async def lifespan(app: FastAPI):
    await migrate_jobs_to_global()
    await init_jsearch_scheduler()
    await init_indeed_scheduler()
    await register_with_eureka()
    yield
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_migration_signature.py -v`
Expected: PASS

- [ ] **Step 5: Runtime verification (dev Mongo)**

Restart the server; confirm no error and that a second run migrates 0:
```bash
python - <<'PY'
import asyncio
from app.services.jobs_service import migrate_jobs_to_global
async def main():
    print("first:", await migrate_jobs_to_global())
    print("second:", await migrate_jobs_to_global())
asyncio.run(main())
PY
```
Expected: second call prints `second: 0` (idempotent).

- [ ] **Step 6: Commit**

```bash
git add app/services/jobs_service.py app/main.py tests/test_migration_signature.py
git commit -m "feat(marketplace): idempotent startup migration folding jobs into GLOBAL pool"
```

---

### Task 6: Global, auto-active indeed scheduler

**Files:**
- Modify: `app/services/indeed_scheduler_service.py` (`init_indeed_scheduler` ~23-26, add global config + registration)
- Modify: `app/routers/indeed_scheduler.py` (endpoints operate on GLOBAL)
- Test: `tests/test_global_indeed_config.py`

**Interfaces:**
- Consumes: `app.constants.GLOBAL_ORG_ID`, `IndeedSchedulerConfig`, existing `start/stop/get_indeed_scheduler_status_for_org`, `_run_indeed_tick`, `_save_scheduler_state`, `_get_scheduler_state`, `scheduler`, `INDEED_SCHEDULER_JOB_ID`.
- Produces: `GLOBAL_INDEED_CONFIG: IndeedSchedulerConfig` (`location="United States"`, `interval_minutes=30`); `init_indeed_scheduler()` registers job id `f"{INDEED_SCHEDULER_JOB_ID}:GLOBAL"` enabled at startup.

- [ ] **Step 1: Write the failing test**

`tests/test_global_indeed_config.py`:
```python
from app.services.indeed_scheduler_service import GLOBAL_INDEED_CONFIG


def test_global_indeed_defaults():
    assert GLOBAL_INDEED_CONFIG.location == "United States"
    assert GLOBAL_INDEED_CONFIG.interval_minutes == 30
    assert len(GLOBAL_INDEED_CONFIG.keywords) == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_global_indeed_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'GLOBAL_INDEED_CONFIG'`

- [ ] **Step 3: Write minimal implementation**

In `app/services/indeed_scheduler_service.py`, add imports + constants near the top (after `scheduler = AsyncIOScheduler(...)`):
```python
from app.constants import GLOBAL_ORG_ID

GLOBAL_INDEED_CONFIG = IndeedSchedulerConfig(
    location="United States",
    interval_minutes=30,
)
GLOBAL_JOB_ID = f"{INDEED_SCHEDULER_JOB_ID}:{GLOBAL_ORG_ID}"
```
Replace `init_indeed_scheduler`:
```python
async def init_indeed_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("Indeed scheduler started")
    await _register_global_indeed_job()


async def _register_global_indeed_job() -> None:
    state = await _get_scheduler_state(GLOBAL_ORG_ID)

    config = GLOBAL_INDEED_CONFIG
    current_index = 0
    if state:
        current_index = int(state.get("current_keyword_index", 0))
        if state.get("config"):
            try:
                config = IndeedSchedulerConfig(**state["config"])
            except Exception:
                config = GLOBAL_INDEED_CONFIG

    scheduler.add_job(
        _run_indeed_tick,
        trigger=IntervalTrigger(minutes=config.interval_minutes),
        id=GLOBAL_JOB_ID,
        kwargs={"org_id": GLOBAL_ORG_ID},
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    await _save_scheduler_state(
        org_id=GLOBAL_ORG_ID,
        enabled=True,
        config=config.model_dump(),
        current_keyword_index=current_index,
    )
    logger.info("Global indeed scheduler registered (interval=%dm)", config.interval_minutes)
```
In `app/routers/indeed_scheduler.py`, add `from app.constants import GLOBAL_ORG_ID` and change the three endpoints to use `GLOBAL_ORG_ID` instead of `current_user.org_id`:
```python
    return await get_indeed_scheduler_status_for_org(org_id=GLOBAL_ORG_ID)
```
```python
        return await start_indeed_scheduler_for_org(org_id=GLOBAL_ORG_ID, config=payload)
```
```python
        return await stop_indeed_scheduler_for_org(org_id=GLOBAL_ORG_ID)
```
(Keep `current_user: CurrentUser = Depends(get_current_user)` on each for auth.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_global_indeed_config.py -v`
Expected: PASS

- [ ] **Step 5: Runtime verification (dev Mongo)**

Restart the server. Query status with any valid local token:
```bash
curl -s "http://127.0.0.1:8099/api/v1/marketplace/indeed/scheduler/status" -H "Authorization: Bearer $TOK" | python -m json.tool
```
Expected: `"enabled": true`, `"running": true`, `"job_id": "indeed_auto_pull:GLOBAL"`, `"next_run_at"` a timestamp ~30 min out, `"interval_minutes": 30`.

- [ ] **Step 6: Commit**

```bash
git add app/services/indeed_scheduler_service.py app/routers/indeed_scheduler.py tests/test_global_indeed_config.py
git commit -m "feat(marketplace): global auto-active indeed scheduler"
```

---

### Task 7: Full local E2E + deploy notes

**Files:**
- Modify: `README.md` (or `docs/`) — deploy note about `--min-instances=1`

**Interfaces:** none (verification + docs).

- [ ] **Step 1: Full local run-through**

Restart the server fresh (simulates a redeploy). Run the whole suite:
```bash
python -m pytest tests/ -v
```
Expected: all pass.

Then confirm, with a local token whose org has never scraped:
```bash
# scheduler active by default after a fresh start
curl -s .../indeed/scheduler/status -H "Authorization: Bearer $TOK" | python -m json.tool   # running:true
# reads are global
curl -s ".../jobs/counts" -H "Authorization: Bearer $TOK"        # non-zero total
curl -s ".../jobs/?limit=1" -H "Authorization: Bearer $TOK"      # returns a job
```
Expected: scheduler running; counts/list non-empty for an org that never scraped.

- [ ] **Step 2: Document the required deploy flag**

Add to `README.md` a "Deploy" note:
```
The indeed scheduler runs in-process (APScheduler). Cloud Run must keep one
instance warm or the scheduler stops between ticks. Deploy with:

  gcloud run deploy <marketplace-service> --source . --region asia-south1 --min-instances=1
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(marketplace): require --min-instances=1 for the in-process scheduler"
```

- [ ] **Step 4: Post-deploy prod verification (manual, after user deploys)**

After the user deploys the marketplace with `--min-instances=1`:
- `GET /api/v1/marketplace/indeed/scheduler/status` (subscribed org token) → `running:true`, `next_run_at` set; after ~30 min `last_run_at` advances and `last_result.total_fetched` > 0.
- A DIFFERENT subscribed org's token → `/counts` returns the same totals (proves the common pool).
- `/jobs/` returns jobs for that second org.

---

## Notes for the implementer
- The dev Mongo (`.env`) is a shared Atlas dev cluster — the migration will fold its existing jobs to GLOBAL. That is expected and idempotent.
- Do not add `--min-instances=1` yourself; it is a deploy-time flag the user sets. Only document it.
- Keep all endpoints' `get_current_user` dependency — removing it would drop authentication.
