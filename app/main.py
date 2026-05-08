from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import py_eureka_client.eureka_client as eureka_client
import logging

from app.routers.jobs import router as jobs_router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    try:
        await eureka_client.init_async(
            eureka_server=settings.EUREKA_SERVER,
            app_name="marketplace-service",
            instance_port=settings.APP_PORT,
            instance_host=settings.EUREKA_HOST,  # must be the Cloud Run hostname
            instance_ip=settings.EUREKA_HOST,  # ← add this line

        )
        logger.info(
            "✅ Registered with Eureka as 'marketplace-service' on port %d",
            settings.APP_PORT
        )
    except Exception as e:
        logger.warning("⚠️ Eureka registration failed: %s", e)

    yield

    # ── Shutdown ──
    try:
        await eureka_client.stop_async()
        logger.info("✅ Deregistered from Eureka")
    except Exception:
        pass


def create_app() -> FastAPI:
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
            "service": "marketplace-service",
            "env": settings.APP_ENV,
        })

    return app


app = create_app()