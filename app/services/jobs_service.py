import asyncio
import logging
import math
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd

from app.database import get_db
from app.models.scraped_job import (
    JobSearchRequest,
    JSearchRequest,
    ScrapedJob,
    LocationModel,
    SalaryModel,
    ScrapedJobListResponse,
    JSearchFetchResponse,
    FetchStatusResponse,
)
from app.services.jobspy_service import jobspy_search
from app.services.jsearch_service import jsearch_search, jsearch_search_v2

logger = logging.getLogger(__name__)

FETCH_COOLDOWN_MINUTES = 15


def _normalize_dates(data: dict) -> dict:
    for k, v in list(data.items()):
        if isinstance(v, date) and not isinstance(v, datetime):
            data[k] = datetime.combine(v, datetime.min.time())
    return data


def _hours_since(dt: datetime) -> int:
    delta = datetime.utcnow() - dt
    return max(int(delta.total_seconds() / 3600), 1)


async def _get_fetch_meta(
    org_id: str,
    site: str,
    keywords: Optional[str] = None,
    location: Optional[str] = None,
) -> Optional[dict]:
    db = get_db()

    if site == "indeed" and keywords is not None and location is not None:
        query: Dict[str, Any] = {
            "org_id": org_id,
            "site": site,
            "keywords": keywords,
            "location": location,
        }
    else:
        query = {
            "org_id": org_id,
            "site": site,
        }

    return await db.site_fetch_meta.find_one(query)


async def _update_fetch_meta(
    org_id: str,
    site: str,
    keywords: str,
    location: str,
    next_cursor: Optional[str] = None,
):
    db = get_db()

    if site == "indeed":
        query: Dict[str, Any] = {
            "org_id": org_id,
            "site": site,
            "keywords": keywords,
            "location": location,
        }
    else:
        query = {
            "org_id": org_id,
            "site": site,
        }

    update_data: Dict[str, Any] = {
        "last_fetched_at": datetime.utcnow(),
        "last_keywords": keywords,
        "last_location": location,
    }

    if next_cursor is not None:
        update_data["last_cursor"] = next_cursor

    await db.site_fetch_meta.update_one(
        query,
        {"$set": update_data},
        upsert=True,
    )


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_posted_at(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    return None


def _row_to_scraped_job(row: pd.Series, org_id: str) -> ScrapedJob:
    location = LocationModel(
        raw=row.get("location"),
        city=row.get("city"),
        state=row.get("state"),
        country=row.get("country"),
        is_remote=bool(row.get("is_remote", False)),
    )

    salary = SalaryModel(
        min=_safe_float(row.get("min_amount")),
        max=_safe_float(row.get("max_amount")),
        currency=row.get("currency"),
        interval=row.get("interval"),
        source=row.get("salary_source"),
    )

    external_id = row.get("job_id") or row.get("id")

    skills: List[str] = []
    raw_skills = row.get("skills")
    if isinstance(raw_skills, list):
        skills = [str(s).strip() for s in raw_skills if str(s).strip()]
    elif isinstance(raw_skills, str):
        skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

    source_site = str(row.get("site", row.get("source", "")))
    raw_dict = _normalize_dates(row.to_dict())

    return ScrapedJob(
        org_id=org_id,
        source_site=source_site,
        external_id=str(external_id) if external_id else None,
        title=row.get("title"),
        company_name=row.get("company"),
        company_url=row.get("company_url"),
        location=location,
        salary=salary,
        job_type=row.get("job_type"),
        description=row.get("description"),
        posted_at=_parse_posted_at(row.get("date_posted")),
        url=row.get("job_url", row.get("url")),
        skills=skills,
        scraped_at=datetime.utcnow(),
        raw=raw_dict,
    )


def _jsearch_job_to_scraped(raw: Dict[str, Any], org_id: str) -> ScrapedJob:
    location_raw = raw.get("job_location")
    if not location_raw:
        location_raw = ", ".join(
            filter(None, [raw.get("job_city"), raw.get("job_state"), raw.get("job_country")])
        ) or None

    is_remote = bool(raw.get("job_is_remote", False))
    if raw.get("work_arrangement") == "remote":
        is_remote = True

    salary = SalaryModel(
        min=_safe_float(raw.get("job_min_salary")),
        max=_safe_float(raw.get("job_max_salary")),
        currency=raw.get("job_salary_currency") or raw.get("salary_currency"),
        interval=raw.get("job_salary_period"),
        source="jsearch",
    )

    posted_at: Optional[datetime] = None
    raw_ts = raw.get("job_posted_at_datetime_utc")
    if raw_ts:
        try:
            posted_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    skills: List[str] = []
    required_technologies = raw.get("required_technologies") or []
    preferred_technologies = raw.get("preferred_technologies") or []

    if isinstance(required_technologies, list):
        skills.extend([str(x).strip() for x in required_technologies if str(x).strip()])
    if isinstance(preferred_technologies, list):
        skills.extend([str(x).strip() for x in preferred_technologies if str(x).strip()])

    if not skills:
        highlights = raw.get("job_highlights") or {}
        qualifications = highlights.get("Qualifications", [])
        if isinstance(qualifications, list):
            skills = [str(x).strip() for x in qualifications if str(x).strip()]

    deduped_skills = list(dict.fromkeys(skills))

    return ScrapedJob(
        org_id=org_id,
        source_site="jsearch",
        external_id=str(raw.get("job_id")) if raw.get("job_id") else None,
        title=raw.get("job_title"),
        company_name=raw.get("employer_name"),
        company_url=raw.get("employer_website"),
        location=LocationModel(
            raw=location_raw,
            city=raw.get("job_city"),
            state=raw.get("job_state"),
            country=raw.get("job_country"),
            is_remote=is_remote,
        ),
        salary=salary,
        job_type=raw.get("job_employment_type"),
        description=raw.get("job_description"),
        posted_at=posted_at,
        url=raw.get("job_apply_link") or raw.get("job_google_link"),
        skills=deduped_skills,
        scraped_at=datetime.utcnow(),
        raw=raw,
    )


def _job_identity_query(job: ScrapedJob, org_id: str) -> Dict[str, Any]:
    if job.external_id:
        return {
            "org_id": org_id,
            "source_site": job.source_site,
            "external_id": job.external_id,
        }

    return {
        "org_id": org_id,
        "source_site": job.source_site,
        "title": job.title,
        "company_name": job.company_name,
        "url": job.url,
    }


async def _upsert_job(
    jobs_coll,
    job: ScrapedJob,
    org_id: str,
    now: datetime,
) -> Tuple[ScrapedJob, bool]:
    query = _job_identity_query(job, org_id)
    existing = await jobs_coll.find_one(query)

    doc = job.model_dump(exclude={"id"})

    if existing:
        doc["updated_at"] = now
        await jobs_coll.update_one(
            {"_id": existing["_id"]},
            {"$set": doc},
        )
        job.id = str(existing["_id"])
        return job, False

    doc["created_at"] = now
    doc["updated_at"] = now
    result = await jobs_coll.insert_one(doc)
    job.id = str(result.inserted_id)
    return job, True


async def get_fetch_status(org_id: str, sites: List[str]) -> List[FetchStatusResponse]:
    result = []

    for site in sites:
        db = get_db()

        if site == "indeed":
            meta = await db.site_fetch_meta.find_one(
                {"org_id": org_id, "site": site},
                sort=[("last_fetched_at", -1)],
            )
        else:
            meta = await _get_fetch_meta(org_id, site)

        if not meta:
            result.append(
                FetchStatusResponse(
                    site=site,
                    last_fetched_at=None,
                    next_allowed_at=None,
                    can_fetch=True,
                    hours_old=None,
                )
            )
            continue

        last = meta["last_fetched_at"]
        next_allowed = last + timedelta(minutes=FETCH_COOLDOWN_MINUTES)
        can_fetch = datetime.utcnow() >= next_allowed

        result.append(
            FetchStatusResponse(
                site=site,
                last_fetched_at=last,
                next_allowed_at=next_allowed,
                can_fetch=can_fetch,
                hours_old=_hours_since(last) if can_fetch else None,
            )
        )

    return result


async def search_and_store_jobs(payload: JobSearchRequest, org_id: str) -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs
    all_jobs: List[ScrapedJob] = []
    now = datetime.utcnow()
    cooldown = timedelta(minutes=FETCH_COOLDOWN_MINUTES)

    for site in payload.sites:
        if site == "indeed":
            meta = await _get_fetch_meta(
                org_id,
                site,
                keywords=payload.keywords,
                location=payload.location,
            )
        else:
            meta = await _get_fetch_meta(org_id, site)

        if meta:
            last = meta["last_fetched_at"]
            if now - last < cooldown:
                logger.info(
                    "Skipping %s due to cooldown for org=%s keyword=%s location=%s",
                    site,
                    org_id,
                    payload.keywords,
                    payload.location,
                )
                continue

        hours_old = _hours_since(meta["last_fetched_at"]) if meta else (payload.hours_old or 72)
        single_payload = payload.model_copy(update={"sites": [site], "hours_old": hours_old})

        df = jobspy_search(single_payload)
        if not df.empty:
            for _, row in df.iterrows():
                job = _row_to_scraped_job(row, org_id=org_id)
                job, _ = await _upsert_job(jobs_coll, job, org_id, now)
                all_jobs.append(job)

        await _update_fetch_meta(
            org_id=org_id,
            site=site,
            keywords=payload.keywords,
            location=payload.location,
        )

    return ScrapedJobListResponse(total=len(all_jobs), jobs=all_jobs)


async def search_and_store_jsearch_jobs(payload: JSearchRequest, org_id: str) -> JSearchFetchResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs
    now = datetime.utcnow()

    query = f"{payload.keywords} jobs in {payload.location}".strip()
    language = payload.language or ("en" if payload.country.lower() == "us" else None)

    logger.info(
        "Starting JSearch fetch org_id=%s query=%s country=%s language=%s use_cursor=%s",
        org_id,
        query,
        payload.country,
        language,
        payload.use_cursor,
    )

    next_cursor: Optional[str] = None

    if payload.use_cursor:
        raw_jobs, next_cursor = await jsearch_search_v2(
            query=query,
            num_pages=payload.num_pages,
            cursor=payload.cursor,
            country=payload.country,
            language=language,
            date_posted=payload.date_posted,
            work_from_home=payload.work_from_home,
            employment_types=payload.employment_types,
            job_requirements=payload.job_requirements,
            radius=payload.radius,
            exclude_job_publishers=payload.exclude_job_publishers,
        )
    else:
        raw_jobs = await jsearch_search(
            query=query,
            num_pages=payload.num_pages,
            country=payload.country,
            language=language,
            date_posted=payload.date_posted,
            work_from_home=payload.work_from_home,
            employment_types=payload.employment_types,
            job_requirements=payload.job_requirements,
            radius=payload.radius,
            exclude_job_publishers=payload.exclude_job_publishers,
        )

    stored_jobs: List[ScrapedJob] = []
    new_count = 0

    for raw in raw_jobs:
        job = _jsearch_job_to_scraped(raw, org_id=org_id)
        job, inserted = await _upsert_job(jobs_coll, job, org_id, now)
        if inserted:
            new_count += 1
        stored_jobs.append(job)

    updated_count = len(stored_jobs) - new_count

    await _update_fetch_meta(
        org_id=org_id,
        site="jsearch",
        keywords=payload.keywords,
        location=payload.location,
        next_cursor=next_cursor,
    )

    logger.info(
        "Completed JSearch fetch org_id=%s fetched=%d stored=%d new=%d",
        org_id,
        len(raw_jobs),
        len(stored_jobs),
        new_count,
    )

    return JSearchFetchResponse(
        fetched_count=len(raw_jobs),
        stored_count=len(stored_jobs),
        new_count=new_count,
        updated_count=updated_count,
        next_cursor=next_cursor,
        jobs=stored_jobs,
    )

async def list_scraped_jobs(
    org_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    site: Optional[str] = None,
    skills: Optional[str] = None,
) -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs

    query: Dict[str, Any] = {}

    if org_id:
        query["org_id"] = org_id

    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"company_name": {"$regex": keyword, "$options": "i"}},
        ]

    if location:
        query["location.raw"] = {"$regex": location, "$options": "i"}

    if job_type:
        query["job_type"] = {"$regex": job_type, "$options": "i"}

    if site:
        query["source_site"] = site

    if skills:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        if skill_list:
            query["skills"] = {"$in": skill_list}

    total = await jobs_coll.count_documents(query)
    cursor = jobs_coll.find(query).sort("scraped_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    jobs: List[ScrapedJob] = []
    for doc in docs:
        jobs.append(
            ScrapedJob(
                id=str(doc["_id"]),
                org_id=doc["org_id"],
                source_site=doc.get("source_site", ""),
                external_id=doc.get("external_id"),
                title=doc.get("title"),
                company_name=doc.get("company_name"),
                company_url=doc.get("company_url"),
                location=LocationModel(**doc.get("location", {})),
                salary=SalaryModel(**doc.get("salary", {})),
                job_type=doc.get("job_type"),
                description=doc.get("description"),
                posted_at=doc.get("posted_at"),
                url=doc.get("url"),
                skills=doc.get("skills", []),
                scraped_at=doc.get("scraped_at", doc.get("created_at", datetime.utcnow())),
                raw=doc.get("raw", {}),
            )
        )

    return ScrapedJobListResponse(total=total, jobs=jobs)

async def get_job_counts(
    org_id: str,
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    is_remote: Optional[str] = None,
    date_posted: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    jobs_coll = db.scraped_jobs

    base_query: Dict[str, Any] = {"org_id": org_id}

    if keyword:
        base_query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"company_name": {"$regex": keyword, "$options": "i"}},
        ]
    if location:
        base_query["location.raw"] = {"$regex": location, "$options": "i"}
    if is_remote:
        base_query["location.is_remote"] = is_remote.lower() == "true"

    job_types = [
        "fulltime",
        "contract",
        "c2c",
        "w2",
        "c2h",
        "contract_to_hire",
        "parttime",
        "internship",
    ]
    all_sites = ["google", "glassdoor", "zip_recruiter", "indeed", "jsearch"]

    async def count(extra: Dict[str, Any] = {}) -> int:
        return await jobs_coll.count_documents({**base_query, **extra})

    all_count, *site_counts = await asyncio.gather(
        count(),
        *[count({"source_site": site}) for site in all_sites],
    )

    site_job_type_counts = await asyncio.gather(
        *[
            count({"source_site": site, "job_type": {"$regex": jt, "$options": "i"}})
            for site in all_sites
            for jt in job_types
        ]
    )

    sites = dict(zip(all_sites, site_counts))

    site_job_types: Dict[str, Dict[str, int]] = {}
    idx = 0
    for site in all_sites:
        site_job_types[site] = {}
        for jt in job_types:
            site_job_types[site][jt] = site_job_type_counts[idx]
            idx += 1

    return {
        "all": all_count,
        "sites": sites,
        "siteJobTypes": site_job_types,
    }

async def get_all_public_jobs() -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs

    docs = await jobs_coll.find({}).to_list(length=None)  # NO sort

    jobs: List[ScrapedJob] = []
    for doc in docs:
        location_data = doc.get("location") or {}
        salary_data = doc.get("salary") or {}

        if not isinstance(location_data, dict):
            location_data = {}
        if not isinstance(salary_data, dict):
            salary_data = {}

        jobs.append(
            ScrapedJob(
                id=str(doc.get("_id")),
                org_id=doc.get("org_id", ""),
                source_site=doc.get("source_site", ""),
                external_id=doc.get("external_id"),
                title=doc.get("title"),
                company_name=doc.get("company_name"),
                company_url=doc.get("company_url"),
                location=LocationModel(**location_data),
                salary=SalaryModel(**salary_data),
                job_type=doc.get("job_type"),
                description=doc.get("description"),
                posted_at=doc.get("posted_at"),
                url=doc.get("url"),
                skills=doc.get("skills", []) if isinstance(doc.get("skills"), list) else [],
                scraped_at=doc.get("scraped_at") or doc.get("created_at") or datetime.utcnow(),
                raw=doc.get("raw", {}),
            )
        )

    return ScrapedJobListResponse(total=len(jobs), jobs=jobs)