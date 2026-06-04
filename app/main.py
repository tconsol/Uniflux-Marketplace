from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.eureka_client import register_with_eureka, deregister_from_eureka
from app.routers.jobs import router as jobs_router
from app.routers.indeed_scheduler import router as indeed_scheduler_router
from app.services.jsearch_scheduler_service import (
    init_jsearch_scheduler,
    shutdown_jsearch_scheduler,
)
from app.services.indeed_scheduler_service import (
    init_indeed_scheduler,
    shutdown_indeed_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_jsearch_scheduler()
    await init_indeed_scheduler()
    await register_with_eureka()
    yield
    await deregister_from_eureka()
    await shutdown_indeed_scheduler()
    await shutdown_jsearch_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(indeed_scheduler_router)


@app.get("/health", tags=["Health"])
async def health():
    return JSONResponse(
        {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "env": settings.APP_ENV,
        }
    )