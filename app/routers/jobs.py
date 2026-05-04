from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth_middleware import get_current_user, CurrentUser
from app.models.scraped_job import JobSearchRequest, ScrapedJobListResponse
from app.services.jobs_service import search_and_store_jobs, list_scraped_jobs

router = APIRouter(prefix="/api/v1/marketplace/jobs", tags=["Marketplace Jobs"])


@router.post("/search", response_model=ScrapedJobListResponse)
async def search_jobs(
    payload: JobSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger a scrape via JobSpy, normalize, store into Mongo, and return the jobs.
    """
    try:
        return await search_and_store_jobs(payload, org_id=current_user.org_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scraping error: {exc}")


@router.get("/", response_model=ScrapedJobListResponse)
async def get_scraped_jobs(
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List recently scraped jobs for this org from marketplace DB.
    """
    return await list_scraped_jobs(org_id=current_user.org_id, limit=limit)