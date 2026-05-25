# app/services/jsearch_service.py

import httpx
import logging
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

JSEARCH_BASE_URL = "https://api.openwebninja.com/jsearch"


def _headers() -> Dict[str, str]:
    if not settings.RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY is not set in .env")
    return {"x-api-key": settings.RAPIDAPI_KEY}


async def jsearch_search(
    query: str,
    num_pages: int = 1,
    page: int = 1,
    country: str = "us",
    language: Optional[str] = None,
    date_posted: str = "all",
    work_from_home: bool = False,
    employment_types: Optional[str] = None,
    job_requirements: Optional[str] = None,
    radius: Optional[float] = None,
    exclude_job_publishers: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Calls GET /search — page-based pagination.
    Returns the raw list of job dicts from data[].
    """
    params: Dict[str, Any] = {
        "query": query,
        "page": page,
        "num_pages": num_pages,
        "country": country,
        "date_posted": date_posted,
        "work_from_home": str(work_from_home).lower(),
    }
    if language:
        params["language"] = language
    if employment_types:
        params["employment_types"] = employment_types
    if job_requirements:
        params["job_requirements"] = job_requirements
    if radius is not None:
        params["radius"] = radius
    if exclude_job_publishers:
        params["exclude_job_publishers"] = exclude_job_publishers

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/search",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()

    data = resp.json()
    jobs: List[Dict[str, Any]] = data.get("data", [])
    logger.debug("JSearch /search returned %d jobs", len(jobs))
    return jobs


async def jsearch_search_v2(
    query: str,
    num_pages: int = 1,
    cursor: Optional[str] = None,
    country: str = "us",
    language: Optional[str] = None,
    date_posted: str = "all",
    work_from_home: bool = False,
    employment_types: Optional[str] = None,
    job_requirements: Optional[str] = None,
    radius: Optional[float] = None,
    exclude_job_publishers: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Calls GET /search-v2 — cursor-based pagination.
    Returns (jobs_list, next_cursor).
    Pass next_cursor as cursor on the next call to paginate.
    """
    params: Dict[str, Any] = {
        "query": query,
        "num_pages": num_pages,
        "country": country,
        "date_posted": date_posted,
        "work_from_home": str(work_from_home).lower(),
    }
    if cursor:
        params["cursor"] = cursor
    if language:
        params["language"] = language
    if employment_types:
        params["employment_types"] = employment_types
    if job_requirements:
        params["job_requirements"] = job_requirements
    if radius is not None:
        params["radius"] = radius
    if exclude_job_publishers:
        params["exclude_job_publishers"] = exclude_job_publishers

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/search-v2",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()

    body = resp.json()
    # v2 response: { "data": { "jobs": [...], "cursor": "..." } }
    data_block: Dict[str, Any] = body.get("data", {})
    jobs: List[Dict[str, Any]] = data_block.get("jobs", [])
    next_cursor: Optional[str] = data_block.get("cursor")
    logger.debug("JSearch /search-v2 returned %d jobs, next_cursor=%s", len(jobs), next_cursor)
    return jobs, next_cursor


async def jsearch_job_details(
    job_id: str,
    country: str = "us",
    language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calls GET /job-details for a single job_id.
    Returns the first item in data[] or None.
    """
    params: Dict[str, Any] = {"job_id": job_id, "country": country}
    if language:
        params["language"] = language

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/job-details",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()

    data: List[Dict[str, Any]] = resp.json().get("data", [])
    return data[0] if data else None


async def jsearch_estimated_salary(
    job_title: str,
    location: str,
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> List[Dict[str, Any]]:
    """
    Calls GET /estimated-salary.
    Returns list of salary estimate dicts.
    """
    params = {
        "job_title": job_title,
        "location": location,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/estimated-salary",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
    return resp.json().get("data", [])


async def jsearch_company_salary(
    company: str,
    job_title: str,
    location: Optional[str] = None,
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> List[Dict[str, Any]]:
    """
    Calls GET /company-job-salary.
    Returns list of company salary estimate dicts.
    """
    params: Dict[str, Any] = {
        "company": company,
        "job_title": job_title,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    }
    if location:
        params["location"] = location

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/company-job-salary",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
    return resp.json().get("data", [])