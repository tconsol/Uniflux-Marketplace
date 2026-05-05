from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from app.middleware.auth_middleware import get_current_user, CurrentUser
from app.models.scraped_job import JobSearchRequest, ScrapedJobListResponse, FetchStatusResponse
from app.services.jobs_service import (
    search_and_store_jobs,
    list_scraped_jobs,
    get_fetch_status,
)

router = APIRouter(prefix="/api/v1/marketplace/jobs", tags=["Marketplace Jobs"])


@router.post("/search", response_model=ScrapedJobListResponse)
async def search_jobs(
    payload: JobSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await search_and_store_jobs(payload, org_id=current_user.org_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scraping error: {exc}")


@router.get("/fetch-status", response_model=List[FetchStatusResponse])
async def fetch_status(
    sites: str = Query("indeed,linkedin,glassdoor,zip_recruiter,google"),
    current_user: CurrentUser = Depends(get_current_user),
):
    site_list = [s.strip() for s in sites.split(",") if s.strip()]
    return await get_fetch_status(org_id=current_user.org_id, sites=site_list)


@router.get("/", response_model=ScrapedJobListResponse)
async def get_scraped_jobs(
    limit: int = Query(50, ge=1, le=100),      # 50 per page
    skip: int = Query(0, ge=0),                # offset-based pagination
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