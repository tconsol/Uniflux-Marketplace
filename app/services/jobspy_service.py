import logging
import os

import pandas as pd
from jobspy import scrape_jobs

from app.models.scraped_job import JobSearchRequest

logger = logging.getLogger(__name__)

PROXY_URL = os.getenv("PROXY_URL")

def jobspy_search(payload: JobSearchRequest) -> pd.DataFrame:
    params = {
        "site_name": payload.sites,
        "search_term": payload.keywords,
        "location": payload.location,
        "results_wanted": payload.results_wanted,
        "hours_old": payload.hours_old,
        "country_indeed": payload.country_indeed,
        "remote_only": payload.remote_only,
        "proxies": [PROXY_URL] if PROXY_URL else None,
        "ca_cert": None,
    }

    logger.debug("JOBSPY PARAMS: %s", params)
    jobs_df = scrape_jobs(**{k: v for k, v in params.items() if v is not None})
    logger.debug("JOBSPY ROWS: %d", len(jobs_df))

    jobs_df = jobs_df.where(pd.notna(jobs_df), other=None)

    return jobs_df