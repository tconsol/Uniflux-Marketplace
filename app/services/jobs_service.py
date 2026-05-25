from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any

import pandas as pd

from app.database import get_db
from app.models.scraped_job import (
    JobSearchRequest,
    JSearchRequest,
    ScrapedJob,
    LocationModel,
    SalaryModel,
    ScrapedJobListResponse,
    FetchStatusResponse,
)
from app.services.jobspy_service import jobspy_search
from app.services.jsearch_service import jsearch_search, jsearch_search_v2

FETCH_COOLDOWN_MINUTES = 15


def _normalize_dates(data: dict) -> dict:
    for k, v in list(data.items()):
        if isinstance(v, date) and not isinstance(v, datetime):
            data[k] = datetime.combine(v, datetime.min.time())
    return data


def _hours_since(dt: datetime) -> int:
    delta = datetime.utcnow() - dt
    return max(int(delta.total_seconds() / 3600), 1)


async def _get_fetch_meta(org_id: str, site: str) -> Optional[dict]:
    db = get_db()
    return await db.site_fetch_meta.find_one({"org_id": org_id, "site": site})


async def _update_fetch_meta(org_id: str, site: str, keywords: str, location: str):
    db = get_db()
    await db.site_fetch_meta.update_one(
        {"org_id": org_id, "site": site},
        {"$set": {
            "last_fetched_at": datetime.utcnow(),
            "last_keywords": keywords,
            "last_location": location,
        }},
        upsert=True,
    )


def _row_to_scraped_job(row: pd.Series, org_id: str) -> ScrapedJob:
    location = LocationModel(
        raw=row.get("location"),
        city=row.get("city"),
        state=row.get("state"),
        country=row.get("country"),
        is_remote=bool(row.get("is_remote", False)),
    )
    salary = SalaryModel(
        min=row.get("min_amount"),
        max=row.get("max_amount"),
        currency=row.get("currency"),
        interval=row.get("interval"),
        source=row.get("salary_source"),
    )

    posted_at = None
    dt = row.get("date_posted")
    if isinstance(dt, datetime):
        posted_at = dt
    elif isinstance(dt, str):
        try:
            posted_at = datetime.fromisoformat(dt)
        except ValueError:
            pass

    external_id = row.get("job_id") or row.get("id")

    skills: List[str] = []
    raw_skills = row.get("skills")
    if isinstance(raw_skills, list):
        skills = [str(s) for s in raw_skills]
    elif isinstance(raw_skills, str):
        skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

    source_site = str(row.get("site", row.get("source", "")))
    raw_dict = _normalize_dates(row.to_dict())

    return ScrapedJob(
        org_id=org_id,
        source_site=source_site,
        external_id=external_id,
        title=row.get("title"),
        company_name=row.get("company"),
        company_url=row.get("company_url"),
        location=location,
        salary=salary,
        job_type=row.get("job_type"),
        description=row.get("description"),
        posted_at=posted_at,
        url=row.get("job_url", row.get("url")),
        skills=skills,
        scraped_at=datetime.utcnow(),
        raw=raw_dict,
    )


def _jsearch_job_to_scraped(raw: Dict[str, Any], org_id: str) -> ScrapedJob:
    location = LocationModel(
        raw=raw.get("job_location") or ", ".join(filter(None, [
            raw.get("job_city"),
            raw.get("job_state"),
            raw.get("job_country"),
        ])),
        city=raw.get("job_city"),
        state=raw.get("job_state"),
        country=raw.get("job_country"),
        is_remote=bool(raw.get("job_is_remote", False)),
    )

    salary = SalaryModel(
        min=raw.get("job_min_salary"),
        max=raw.get("job_max_salary"),
        currency=raw.get("job_salary_currency"),
        interval=raw.get("job_salary_period"),
        source="jsearch",
    )

    posted_at: Optional[datetime] = None
    raw_ts = raw.get("job_posted_at_datetime_utc")
    if raw_ts:
        try:
            posted_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except ValueError:
            pass

    highlights = raw.get("job_highlights") or {}
    qualifications = highlights.get("Qualifications", [])
    if not isinstance(qualifications, list):
        qualifications = []

    return ScrapedJob(
        org_id=org_id,
        source_site="jsearch",
        external_id=raw.get("job_id"),
        title=raw.get("job_title"),
        company_name=raw.get("employer_name"),
        company_url=raw.get("employer_website"),
        location=location,
        salary=salary,
        job_type=raw.get("job_employment_type"),
        description=raw.get("job_description"),
        posted_at=posted_at,
        url=raw.get("job_apply_link") or raw.get("job_google_link"),
        skills=[str(x) for x in qualifications],
        scraped_at=datetime.utcnow(),
        raw=raw,
    )


async def _upsert_job(jobs_coll, job: ScrapedJob, org_id: str, now: datetime) -> ScrapedJob:
    query = {
        "org_id": org_id,
        "source_site": job.source_site,
        "external_id": job.external_id,
    }
    existing = await jobs_coll.find_one(query)
    if existing:
        await jobs_coll.update_one(
            {"_id": existing["_id"]},
            {"$set": {**job.model_dump(exclude={"id"}), "updated_at": now}},
        )
        job.id = str(existing["_id"])
    else:
        doc = job.model_dump(exclude={"id"})
        doc["created_at"] = now
        result = await jobs_coll.insert_one(doc)
        job.id = str(result.inserted_id)
    return job


async def get_fetch_status(org_id: str, sites: List[str]) -> List[FetchStatusResponse]:
    result = []
    for site in sites:
        meta = await _get_fetch_meta(org_id, site)
        if not meta:
            result.append(FetchStatusResponse(
                site=site,
                last_fetched_at=None,
                next_allowed_at=None,
                can_fetch=True,
                hours_old=None,
            ))
        else:
            last = meta["last_fetched_at"]
            next_allowed = last + timedelta(minutes=FETCH_COOLDOWN_MINUTES)
            can_fetch = datetime.utcnow() >= next_allowed
            result.append(FetchStatusResponse(
                site=site,
                last_fetched_at=last,
                next_allowed_at=next_allowed,
                can_fetch=can_fetch,
                hours_old=_hours_since(last) if can_fetch else None,
            ))
    return result


async def search_and_store_jobs(payload: JobSearchRequest, org_id: str) -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs
    all_jobs: List[ScrapedJob] = []
    now = datetime.utcnow()
    cooldown = timedelta(minutes=FETCH_COOLDOWN_MINUTES)

    for site in payload.sites:
        meta = await _get_fetch_meta(org_id, site)
        if meta:
            last = meta["last_fetched_at"]
            if now - last < cooldown:
                continue

        hours_old = _hours_since(meta["last_fetched_at"]) if meta else (payload.hours_old or 72)

        single_payload = payload.model_copy(update={"sites": [site], "hours_old": hours_old})
        df = jobspy_search(single_payload)

        if not df.empty:
            for _, row in df.iterrows():
                job = _row_to_scraped_job(row, org_id=org_id)
                job = await _upsert_job(jobs_coll, job, org_id, now)
                all_jobs.append(job)

        await _update_fetch_meta(org_id, site, payload.keywords, payload.location)

    return ScrapedJobListResponse(total=len(all_jobs), jobs=all_jobs)


async def search_and_store_jsearch_jobs(payload: JSearchRequest, org_id: str) -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs
    all_jobs: List[ScrapedJob] = []
    now = datetime.utcnow()
    cooldown = timedelta(minutes=FETCH_COOLDOWN_MINUTES)

    meta = await _get_fetch_meta(org_id, "jsearch")
    if meta and (now - meta["last_fetched_at"]) < cooldown:
        return await list_scraped_jobs(org_id=org_id, site="jsearch")

    query = f"{payload.keywords} in {payload.location}"

    if payload.use_cursor:
        raw_jobs, _ = await jsearch_search_v2(
            query=query,
            num_pages=payload.num_pages,
            cursor=payload.cursor,
            country=payload.country,
            language=payload.language,
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
            language=payload.language,
            date_posted=payload.date_posted,
            work_from_home=payload.work_from_home,
            employment_types=payload.employment_types,
            job_requirements=payload.job_requirements,
            radius=payload.radius,
            exclude_job_publishers=payload.exclude_job_publishers,
        )

    for raw in raw_jobs:
        job = _jsearch_job_to_scraped(raw, org_id=org_id)
        job = await _upsert_job(jobs_coll, job, org_id, now)
        all_jobs.append(job)

    await _update_fetch_meta(org_id, "jsearch", payload.keywords, payload.location)

    return ScrapedJobListResponse(total=len(all_jobs), jobs=all_jobs)


async def list_scraped_jobs(
    org_id: str,
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

    query: dict = {"org_id": org_id}

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
        job = ScrapedJob(
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
        jobs.append(job)

    return ScrapedJobListResponse(total=total, jobs=jobs)