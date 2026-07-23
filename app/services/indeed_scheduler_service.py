import logging
from datetime import datetime
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.constants import GLOBAL_ORG_ID
from app.database import get_db
from app.models.scraped_job import (
    JobSearchRequest,
    IndeedSchedulerConfig,
    IndeedSchedulerStatusResponse,
)
from app.services.jobs_service import search_and_store_jobs

logger = logging.getLogger(__name__)

INDEED_SCHEDULER_JOB_ID = "indeed_auto_pull"

# Every keyword is fetched in each of these regions per tick. (location, country_indeed name).
INDEED_REGIONS = [("India", "India"), ("United States", "USA")]

scheduler = AsyncIOScheduler(timezone="UTC")

GLOBAL_INDEED_CONFIG = IndeedSchedulerConfig(
    location="United States",
    interval_minutes=30,
)
GLOBAL_JOB_ID = f"{INDEED_SCHEDULER_JOB_ID}:{GLOBAL_ORG_ID}"


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


async def shutdown_indeed_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Indeed scheduler stopped")


async def _save_scheduler_state(
    org_id: str,
    enabled: bool,
    config: Optional[Dict[str, Any]] = None,
    last_run_at: Optional[datetime] = None,
    last_result: Optional[Dict[str, Any]] = None,
    current_keyword_index: Optional[int] = None,
    last_keyword: Optional[str] = None,
) -> None:
    db = get_db()
    update_doc: Dict[str, Any] = {
        "enabled": enabled,
        "updated_at": datetime.utcnow(),
    }

    if config is not None:
        update_doc["config"] = config
    if last_run_at is not None:
        update_doc["last_run_at"] = last_run_at
    if last_result is not None:
        update_doc["last_result"] = last_result
    if current_keyword_index is not None:
        update_doc["current_keyword_index"] = current_keyword_index
    if last_keyword is not None:
        update_doc["last_keyword"] = last_keyword

    await db.indeed_scheduler_meta.update_one(
        {"org_id": org_id},
        {"$set": update_doc},
        upsert=True,
    )


async def _get_scheduler_state(org_id: str) -> Optional[dict]:
    db = get_db()
    return await db.indeed_scheduler_meta.find_one({"org_id": org_id})


async def _run_indeed_tick(org_id: str) -> None:
    state = await _get_scheduler_state(org_id)
    if not state or not state.get("enabled") or not state.get("config"):
        logger.info("Indeed scheduler tick skipped org_id=%s — scheduler disabled", org_id)
        return

    config = IndeedSchedulerConfig(**state["config"])
    keywords = [k.strip() for k in config.keywords if k and k.strip()]

    if not keywords:
        logger.info("Indeed scheduler tick skipped org_id=%s — no keywords configured", org_id)
        await _save_scheduler_state(
            org_id=org_id,
            enabled=True,
            last_run_at=datetime.utcnow(),
            last_result={
                "total_fetched": 0,
                "keyword_ran": None,
                "error": "No keywords configured",
            },
        )
        return

    current_index = int(state.get("current_keyword_index", 0)) % len(keywords)
    keyword = keywords[current_index]
    next_index = (current_index + 1) % len(keywords)

    total_fetched = 0
    errors = []

    # Fetch every keyword in both India and the USA each tick, regardless of the single
    # location/country stored in the config.
    for location, country_indeed in INDEED_REGIONS:
        payload = JobSearchRequest(
            keywords=keyword,
            location=location,
            sites=["indeed"],
            results_wanted=config.results_wanted,
            hours_old=config.hours_old,
            country_indeed=country_indeed,
            remote_only=config.remote_only,
        )

        logger.info(
            "Indeed scheduler tick keyword=%s org_id=%s location=%s country=%s index=%d next_index=%d",
            keyword, org_id, location, country_indeed, current_index, next_index,
        )

        try:
            result = await search_and_store_jobs(payload, org_id=org_id)
            total_fetched += result.total
        except Exception as exc:
            logger.exception(
                "Indeed scheduler tick failed keyword=%s country=%s org_id=%s", keyword, country_indeed, org_id
            )
            errors.append({"keyword": keyword, "country": country_indeed, "error": str(exc)})

    last_result = {
        "total_fetched": total_fetched,
        "keyword_ran": keyword,
        "keyword_index_ran": current_index,
        "next_keyword_index": next_index,
        "errors": errors,
    }

    logger.info(
        "Indeed scheduler tick complete org_id=%s keyword=%s fetched=%d errors=%d",
        org_id, keyword, total_fetched, len(errors),
    )

    await _save_scheduler_state(
        org_id=org_id,
        enabled=True,
        last_run_at=datetime.utcnow(),
        last_result=last_result,
        current_keyword_index=next_index,
        last_keyword=keyword,
    )


async def start_indeed_scheduler_for_org(
    org_id: str,
    config: IndeedSchedulerConfig,
) -> IndeedSchedulerStatusResponse:
    await init_indeed_scheduler()

    job_id = f"{INDEED_SCHEDULER_JOB_ID}:{org_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    state = await _get_scheduler_state(org_id)
    current_keyword_index = 0
    last_run_at = None
    last_result = None

    if state:
        current_keyword_index = int(state.get("current_keyword_index", 0))
        last_run_at = state.get("last_run_at")
        last_result = state.get("last_result")

    scheduler.add_job(
        _run_indeed_tick,
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
        current_keyword_index=current_keyword_index,
        last_run_at=last_run_at,
        last_result=last_result,
    )

    job = scheduler.get_job(job_id)

    return IndeedSchedulerStatusResponse(
        enabled=True,
        running=job is not None,
        job_id=job_id,
        interval_minutes=config.interval_minutes,
        next_run_at=job.next_run_time if job else None,
        last_run_at=last_run_at,
        last_result=last_result,
        config=config,
    )


async def stop_indeed_scheduler_for_org(org_id: str) -> IndeedSchedulerStatusResponse:
    job_id = f"{INDEED_SCHEDULER_JOB_ID}:{org_id}"
    job = scheduler.get_job(job_id)
    if job:
        scheduler.remove_job(job_id)

    state = await _get_scheduler_state(org_id)
    await _save_scheduler_state(org_id=org_id, enabled=False)

    config = None
    interval_minutes = 2
    last_run_at = None
    last_result = None

    if state:
        raw_config = state.get("config")
        if raw_config:
            config = IndeedSchedulerConfig(**raw_config)
            interval_minutes = config.interval_minutes
        last_run_at = state.get("last_run_at")
        last_result = state.get("last_result")

    return IndeedSchedulerStatusResponse(
        enabled=False,
        running=False,
        job_id=job_id,
        interval_minutes=interval_minutes,
        next_run_at=None,
        last_run_at=last_run_at,
        last_result=last_result,
        config=config,
    )


async def get_indeed_scheduler_status_for_org(org_id: str) -> IndeedSchedulerStatusResponse:
    job_id = f"{INDEED_SCHEDULER_JOB_ID}:{org_id}"
    job = scheduler.get_job(job_id)
    state = await _get_scheduler_state(org_id)

    config = None
    interval_minutes = 2
    enabled = False
    last_run_at = None
    last_result = None

    if state:
        enabled = bool(state.get("enabled", False))
        if state.get("config"):
            config = IndeedSchedulerConfig(**state["config"])
            interval_minutes = config.interval_minutes
        last_run_at = state.get("last_run_at")
        last_result = state.get("last_result")

    return IndeedSchedulerStatusResponse(
        enabled=enabled,
        running=job is not None,
        job_id=job_id,
        interval_minutes=interval_minutes,
        next_run_at=job.next_run_time if job else None,
        last_run_at=last_run_at,
        last_result=last_result,
        config=config,
    )