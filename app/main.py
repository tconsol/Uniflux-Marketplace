from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.jobs import router as jobs_router
from app.eureka_client import register_with_eureka, deregister_from_eureka
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    await register_with_eureka()
    yield
    # ── Shutdown ──
    await deregister_from_eureka()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/health", tags=["Health"])
async def health():
    return JSONResponse({
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "env": settings.APP_ENV,
    })