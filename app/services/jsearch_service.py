import logging
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JSEARCH_BASE_URL = "https://api.openwebninja.com/jsearch"


def _get_api_key() -> str:
    api_key = getattr(settings, "OPENWEBNINJA_API_KEY", None)
    if not api_key:
        api_key = getattr(settings, "RAPIDAPI_KEY", None)

    if not api_key:
        raise RuntimeError("OPENWEBNINJA_API_KEY is not set in .env")

    return api_key


def _headers() -> Dict[str, str]:
    return {"x-api-key": _get_api_key()}


def _clean_params(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


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
    params = _clean_params({
        "query": query,
        "page": page,
        "num_pages": num_pages,
        "country": country,
        "language": language,
        "date_posted": date_posted,
        "work_from_home": str(work_from_home).lower(),
        "employment_types": employment_types,
        "job_requirements": job_requirements,
        "radius": radius,
        "exclude_job_publishers": exclude_job_publishers,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("JSearch /search params=%s", params)
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/search",
            headers=_headers(),
            params=params,
        )
        logger.info("JSearch /search status=%s", resp.status_code)
        resp.raise_for_status()

    body = resp.json()
    jobs: List[Dict[str, Any]] = body.get("data", [])
    logger.info("JSearch /search returned jobs=%d", len(jobs))
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
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    params = _clean_params({
        "query": query,
        "num_pages": num_pages,
        "cursor": cursor,
        "country": country,
        "language": language,
        "date_posted": date_posted,
        "work_from_home": str(work_from_home).lower(),
        "employment_types": employment_types,
        "job_requirements": job_requirements,
        "radius": radius,
        "exclude_job_publishers": exclude_job_publishers,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("JSearch /search-v2 params=%s", params)
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/search-v2",
            headers=_headers(),
            params=params,
        )
        logger.info("JSearch /search-v2 status=%s", resp.status_code)
        resp.raise_for_status()

    body = resp.json()
    data_block: Dict[str, Any] = body.get("data", {})
    jobs: List[Dict[str, Any]] = data_block.get("jobs", [])
    next_cursor: Optional[str] = data_block.get("cursor")
    logger.info("JSearch /search-v2 returned jobs=%d next_cursor=%s", len(jobs), next_cursor)
    return jobs, next_cursor


async def jsearch_job_details(
    job_id: str,
    country: str = "us",
    language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    params = _clean_params({
        "job_id": job_id,
        "country": country,
        "language": language,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("JSearch /job-details params=%s", params)
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/job-details",
            headers=_headers(),
            params=params,
        )
        logger.info("JSearch /job-details status=%s", resp.status_code)
        resp.raise_for_status()

    data: List[Dict[str, Any]] = resp.json().get("data", [])
    return data[0] if data else None


async def jsearch_estimated_salary(
    job_title: str,
    location: str,
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> List[Dict[str, Any]]:
    params = _clean_params({
        "job_title": job_title,
        "location": location,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("JSearch /estimated-salary params=%s", params)
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/estimated-salary",
            headers=_headers(),
            params=params,
        )
        logger.info("JSearch /estimated-salary status=%s", resp.status_code)
        resp.raise_for_status()

    return resp.json().get("data", [])


async def jsearch_company_salary(
    company: str,
    job_title: str,
    location: Optional[str] = None,
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> List[Dict[str, Any]]:
    params = _clean_params({
        "company": company,
        "job_title": job_title,
        "location": location,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("JSearch /company-job-salary params=%s", params)
        resp = await client.get(
            f"{JSEARCH_BASE_URL}/company-job-salary",
            headers=_headers(),
            params=params,
        )
        logger.info("JSearch /company-job-salary status=%s", resp.status_code)
        resp.raise_for_status()

    return resp.json().get("data", [])