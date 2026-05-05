import math
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from pydantic import BaseModel, Field, model_validator


JobSite = Literal["linkedin", "indeed", "glassdoor", "zip_recruiter", "google"]


class JobSearchRequest(BaseModel):
    keywords: str = Field(..., min_length=2)
    location: str = Field(..., min_length=2)
    sites: List[JobSite] = Field(default_factory=list)
    results_wanted: int = Field(50, ge=1, le=200)
    hours_old: Optional[int] = Field(None, ge=1, le=720)
    country_indeed: Optional[str] = None
    remote_only: bool = False

    def with_defaults(self, default_sites: List[str]) -> "JobSearchRequest":
        if not self.sites:
            self.sites = default_sites
        return self


class LocationModel(BaseModel):
    raw: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    is_remote: bool = False


class SalaryModel(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = None
    interval: Optional[str] = None
    source: Optional[str] = None


class ScrapedJob(BaseModel):
    id: Optional[str] = None
    org_id: str
    source_site: str
    external_id: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    company_url: Optional[str] = None
    location: LocationModel
    salary: SalaryModel
    job_type: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    url: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    scraped_at: datetime
    raw: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def sanitize_nan(cls, values: dict) -> dict:
        def clean(v):
            if isinstance(v, float) and math.isnan(v):
                return None
            return v
        return {k: clean(v) for k, v in values.items()}


class ScrapedJobListResponse(BaseModel):
    total: int
    jobs: List[ScrapedJob]


class SiteFetchMeta(BaseModel):
    org_id: str
    site: str
    last_fetched_at: datetime
    last_keywords: Optional[str] = None
    last_location: Optional[str] = None


class FetchStatusResponse(BaseModel):
    site: str
    last_fetched_at: Optional[datetime]
    next_allowed_at: Optional[datetime]
    can_fetch: bool
    hours_old: Optional[int]