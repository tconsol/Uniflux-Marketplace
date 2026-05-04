from datetime import datetime, date
from typing import List

import pandas as pd
from bson import ObjectId

from app.database import get_db
from app.models.scraped_job import (
    JobSearchRequest,
    ScrapedJob,
    LocationModel,
    SalaryModel,
    ScrapedJobListResponse,
)
from app.services.jobspy_service import jobspy_search


def _normalize_dates(data: dict) -> dict:
    """
    Ensure any datetime.date values are converted to datetime.datetime
    so Mongo/PyMongo can encode them.
    """
    for k, v in list(data.items()):
        if isinstance(v, date) and not isinstance(v, datetime):
            data[k] = datetime.combine(v, datetime.min.time())
    return data


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
            posted_at = None

    external_id = row.get("job_id") or row.get("id")

    skills: List[str] = []
    raw_skills = row.get("skills")
    if isinstance(raw_skills, list):
        skills = [str(s) for s in raw_skills]
    elif isinstance(raw_skills, str):
        skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

    source_site = str(row.get("site", row.get("source", "")))

    # Normalize raw dict so it does not contain bare datetime.date values
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


async def search_and_store_jobs(payload: JobSearchRequest, org_id: str) -> ScrapedJobListResponse:
    df = jobspy_search(payload)
    if df.empty:
        return ScrapedJobListResponse(total=0, jobs=[])

    db = get_db()
    jobs_coll = db.scraped_jobs

    jobs: List[ScrapedJob] = []

    for _, row in df.iterrows():
        job = _row_to_scraped_job(row, org_id=org_id)

        # Simple de-dupe: org_id + source_site + external_id
        query = {
            "org_id": org_id,
            "source_site": job.source_site,
            "external_id": job.external_id,
        }

        existing = await jobs_coll.find_one(query)
        if existing:
            await jobs_coll.update_one(
                {"_id": existing["_id"]},
                {"$set": {**job.model_dump(exclude={"id"}), "updated_at": datetime.utcnow()}},
            )
            job.id = str(existing["_id"])
        else:
            doc = job.model_dump(exclude={"id"})
            doc["created_at"] = datetime.utcnow()
            result = await jobs_coll.insert_one(doc)
            job.id = str(result.inserted_id)

        jobs.append(job)

    return ScrapedJobListResponse(total=len(jobs), jobs=jobs)


async def list_scraped_jobs(org_id: str, limit: int = 100) -> ScrapedJobListResponse:
    db = get_db()
    jobs_coll = db.scraped_jobs

    cursor = jobs_coll.find({"org_id": org_id}).sort("created_at", -1).limit(limit)
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

    return ScrapedJobListResponse(total=len(jobs), jobs=jobs)