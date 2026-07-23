import logging
from datetime import datetime
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import get_db
from app.models.scraped_job import (
    JSearchRequest,
    JSearchSchedulerConfig,
    JSearchSchedulerStatusResponse,
)
from app.services.jobs_service import search_and_store_jsearch_jobs

logger = logging.getLogger(__name__)

JSEARCH_SCHEDULER_JOB_ID = "jsearch_auto_pull"

# Every keyword is fetched in each of these regions per tick. (location, 2-char country code).
JSEARCH_REGIONS = [("India", "in"), ("United States", "us")]

scheduler = AsyncIOScheduler(timezone="UTC")


async def init_jsearch_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("JSearch scheduler started")


async def shutdown_jsearch_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("JSearch scheduler stopped")


async def _save_scheduler_state(
    org_id: str,
    enabled: bool,
    config: Optional[Dict[str, Any]] = None,
    last_run_at: Optional[datetime] = None,
    last_result: Optional[Dict[str, Any]] = None,
    current_keyword_index: Optional[int] = None,
) -> None:
    db = get_db()
    update_doc: Dict[str, Any] = {"enabled": enabled, "updated_at": datetime.utcnow()}
    if config is not None:
        update_doc["config"] = config
    if last_run_at is not None:
        update_doc["last_run_at"] = last_run_at
    if last_result is not None:
        update_doc["last_result"] = last_result
    if current_keyword_index is not None:
        update_doc["current_keyword_index"] = current_keyword_index

    await db.jsearch_scheduler_meta.update_one(
        {"org_id": org_id},
        {"$set": update_doc},
        upsert=True,
    )


async def _get_scheduler_state(org_id: str) -> Optional[dict]:
    db = get_db()
    return await db.jsearch_scheduler_meta.find_one({"org_id": org_id})


async def _run_jsearch_tick(org_id: str) -> None:
    state = await _get_scheduler_state(org_id)
    if not state or not state.get("enabled") or not state.get("config"):
        logger.info("Scheduler tick skipped org_id=%s — scheduler disabled", org_id)
        return

    config = JSearchSchedulerConfig(**state["config"])
    keywords = [k.strip() for k in config.keywords if k and k.strip()]

    if not keywords:
        logger.info("Scheduler tick skipped org_id=%s — no keywords configured", org_id)
        await _save_scheduler_state(
            org_id=org_id,
            enabled=True,
            last_run_at=datetime.utcnow(),
            last_result={"total_fetched": 0, "keyword_ran": None, "error": "No keywords configured"},
        )
        return

    # One keyword per tick (round-robin), mirroring the Indeed scheduler —
    # firing all keywords every tick multiplied paid JSearch API calls by len(keywords).
    current_index = int(state.get("current_keyword_index", 0)) % len(keywords)
    keyword = keywords[current_index]
    next_index = (current_index + 1) % len(keywords)

    total_fetched = 0
    total_new = 0
    total_stored = 0
    errors = []

    # Fetch every keyword in both India and the USA each tick, regardless of the single
    # location/country stored in the config.
    for location, country in JSEARCH_REGIONS:
        payload = JSearchRequest(
            keywords=keyword,
            location=location,
            country=country,
            language=config.language,
            num_pages=config.num_pages,
            date_posted=config.date_posted,
            work_from_home=config.work_from_home,
            employment_types=config.employment_types,
            job_requirements=config.job_requirements,
            radius=config.radius,
            exclude_job_publishers=config.exclude_job_publishers,
            use_cursor=config.use_cursor,
        )

        logger.info(
            "Scheduler tick keyword=%s org_id=%s location=%s country=%s index=%d next_index=%d",
            keyword, org_id, location, country, current_index, next_index,
        )

        try:
            result = await search_and_store_jsearch_jobs(payload, org_id=org_id)
            total_fetched += result.fetched_count
            total_stored += result.stored_count
            total_new += result.new_count
        except Exception as exc:
            logger.exception(
                "Scheduler tick failed keyword=%s country=%s org_id=%s", keyword, country, org_id
            )
            errors.append({"keyword": keyword, "country": country, "error": str(exc)})

    last_result = {
        "total_fetched": total_fetched,
        "total_stored": total_stored,
        "total_new": total_new,
        "keyword_ran": keyword,
        "keyword_index_ran": current_index,
        "next_keyword_index": next_index,
        "errors": errors,
    }

    logger.info(
        "Scheduler tick complete org_id=%s keyword=%s fetched=%d stored=%d new=%d errors=%d",
        org_id, keyword, total_fetched, total_stored, total_new, len(errors),
    )

    await _save_scheduler_state(
        org_id=org_id,
        enabled=True,
        last_run_at=datetime.utcnow(),
        last_result=last_result,
        current_keyword_index=next_index,
    )

async def start_jsearch_scheduler_for_org(
    org_id: str,
    config: JSearchSchedulerConfig,
) -> JSearchSchedulerStatusResponse:
    await init_jsearch_scheduler()

    job_id = f"{JSEARCH_SCHEDULER_JOB_ID}:{org_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _run_jsearch_tick,
        trigger=IntervalTrigger(minutes=config.interval_minutes),
        id=job_id,
        kwargs={"org_id": org_id},
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    await _save_scheduler_state(
        org_id=org_id,
        enabled=True,
        config=config.model_dump(),
    )

    job = scheduler.get_job(job_id)

    return JSearchSchedulerStatusResponse(
        enabled=True,
        running=job is not None,
        job_id=job_id,
        interval_minutes=config.interval_minutes,
        next_run_at=job.next_run_time if job else None,
        last_run_at=None,
        last_result=None,
        config=config,
    )


async def stop_jsearch_scheduler_for_org(org_id: str) -> JSearchSchedulerStatusResponse:
    job_id = f"{JSEARCH_SCHEDULER_JOB_ID}:{org_id}"
    job = scheduler.get_job(job_id)
    if job:
        scheduler.remove_job(job_id)

    state = await _get_scheduler_state(org_id)
    await _save_scheduler_state(org_id=org_id, enabled=False)

    config = None
    interval_minutes = 5
    last_run_at = None
    last_result = None

    if state:
        raw_config = state.get("config")
        if raw_config:
            config = JSearchSchedulerConfig(**raw_config)
            interval_minutes = config.interval_minutes
        last_run_at = state.get("last_run_at")
        last_result = state.get("last_result")

    return JSearchSchedulerStatusResponse(
        enabled=False,
        running=False,
        job_id=job_id,
        interval_minutes=interval_minutes,
        next_run_at=None,
        last_run_at=last_run_at,
        last_result=last_result,
        config=config,
    )


async def get_jsearch_scheduler_status_for_org(org_id: str) -> JSearchSchedulerStatusResponse:
    job_id = f"{JSEARCH_SCHEDULER_JOB_ID}:{org_id}"
    job = scheduler.get_job(job_id)
    state = await _get_scheduler_state(org_id)

    config = None
    interval_minutes = 5
    enabled = False
    last_run_at = None
    last_result = None

    if state:
        enabled = bool(state.get("enabled", False))
        if state.get("config"):
            config = JSearchSchedulerConfig(**state["config"])
            interval_minutes = config.interval_minutes
        last_run_at = state.get("last_run_at")
        last_result = state.get("last_result")

    return JSearchSchedulerStatusResponse(
        enabled=enabled,
        running=job is not None,
        job_id=job_id,
        interval_minutes=interval_minutes,
        next_run_at=job.next_run_time if job else None,
        last_run_at=last_run_at,
        last_result=last_result,
        config=config,
    )