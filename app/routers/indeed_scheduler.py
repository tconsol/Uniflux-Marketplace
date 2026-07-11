from fastapi import APIRouter, Depends, HTTPException

from app.constants import GLOBAL_ORG_ID
from app.middleware.auth_middleware import get_current_user, require_super_admin, CurrentUser
from app.models.scraped_job import (
    IndeedSchedulerConfig,
    IndeedSchedulerStatusResponse,
)
from app.services.indeed_scheduler_service import (
    start_indeed_scheduler_for_org,
    stop_indeed_scheduler_for_org,
    get_indeed_scheduler_status_for_org,
)

router = APIRouter(prefix="/api/v1/marketplace/indeed/scheduler", tags=["Indeed Scheduler"])


@router.get("/status", response_model=IndeedSchedulerStatusResponse)
async def indeed_scheduler_status(
    current_user: CurrentUser = Depends(get_current_user),
):
    return await get_indeed_scheduler_status_for_org(org_id=GLOBAL_ORG_ID)


@router.post("/start", response_model=IndeedSchedulerStatusResponse)
async def indeed_scheduler_start(
    payload: IndeedSchedulerConfig,
    current_user: CurrentUser = Depends(require_super_admin),
):
    try:
        return await start_indeed_scheduler_for_org(
            org_id=GLOBAL_ORG_ID,
            config=payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Indeed scheduler start error: {exc}") from exc


@router.post("/stop", response_model=IndeedSchedulerStatusResponse)
async def indeed_scheduler_stop(
    current_user: CurrentUser = Depends(require_super_admin),
):
    try:
        return await stop_indeed_scheduler_for_org(org_id=GLOBAL_ORG_ID)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Indeed scheduler stop error: {exc}") from exc