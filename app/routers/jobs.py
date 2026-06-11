from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.auth_middleware import get_current_user, CurrentUser
from app.models.scraped_job import (
    JobSearchRequest,
    JSearchRequest,
    ScrapedJobListResponse,
    JSearchFetchResponse,
    FetchStatusResponse,
)
from app.services.jobs_service import (
    search_and_store_jobs,
    search_and_store_jsearch_jobs,
    list_scraped_jobs,
    get_fetch_status,
    get_job_counts,
)

from app.models.scraped_job import (
    JobSearchRequest,
    JSearchRequest,
    ScrapedJobListResponse,
    JSearchFetchResponse,
    FetchStatusResponse,
    JSearchSchedulerConfig,
    JSearchSchedulerStatusResponse,
)
from app.services.jsearch_scheduler_service import (
    start_jsearch_scheduler_for_org,
    stop_jsearch_scheduler_for_org,
    get_jsearch_scheduler_status_for_org,
)

from app.services.jobs_service import get_all_public_jobs

router = APIRouter(prefix="/api/v1/marketplace/jobs", tags=["Marketplace Jobs"])

@router.get("/public", response_model=ScrapedJobListResponse)
async def get_public_jobs():
    return await get_all_public_jobs()

@router.post("/search", response_model=ScrapedJobListResponse)
async def search_jobs(
    payload: JobSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await search_and_store_jobs(payload, org_id=current_user.org_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scraping error: {exc}") from exc


@router.post("/jsearch", response_model=JSearchFetchResponse)
async def search_jobs_jsearch(
    payload: JSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await search_and_store_jsearch_jobs(payload, org_id=current_user.org_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"JSearch error: {exc}") from exc


@router.get("/fetch-status", response_model=List[FetchStatusResponse])
async def fetch_status(
    sites: str = Query("indeed,linkedin,glassdoor,zip_recruiter,google,jsearch"),
    current_user: CurrentUser = Depends(get_current_user),
):
    site_list = [s.strip() for s in sites.split(",") if s.strip()]
    return await get_fetch_status(org_id=current_user.org_id, sites=site_list)


@router.get("/counts")
async def job_counts(
    keyword: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    is_remote: Optional[str] = Query(None),
    date_posted: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await get_job_counts(
        org_id=current_user.org_id,
        keyword=keyword,
        location=location,
        is_remote=is_remote,
        date_posted=date_posted,
    )


@router.get("/", response_model=ScrapedJobListResponse)
async def get_scraped_jobs(
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    keyword: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    skills: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await list_scraped_jobs(
        org_id=current_user.org_id,
        limit=limit,
        skip=skip,
        keyword=keyword,
        location=location,
        job_type=job_type,
        site=site,
        skills=skills,
    )

@router.get("/jsearch/scheduler/status", response_model=JSearchSchedulerStatusResponse)
async def jsearch_scheduler_status(
    current_user: CurrentUser = Depends(get_current_user),
):
    return await get_jsearch_scheduler_status_for_org(org_id=current_user.org_id)


@router.post("/jsearch/scheduler/start", response_model=JSearchSchedulerStatusResponse)
async def jsearch_scheduler_start(
    payload: JSearchSchedulerConfig,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await start_jsearch_scheduler_for_org(
            org_id=current_user.org_id,
            config=payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scheduler start error: {exc}") from exc


@router.post("/jsearch/scheduler/stop", response_model=JSearchSchedulerStatusResponse)
async def jsearch_scheduler_stop(
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await stop_jsearch_scheduler_for_org(org_id=current_user.org_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scheduler stop error: {exc}") from exc