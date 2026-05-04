from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import py_eureka_client.eureka_client as eureka_client
import logging

from app.routers.jobs import router as jobs_router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: register with Eureka ──
    try:
        await eureka_client.init_async(
            eureka_server=settings.EUREKA_SERVER,
            app_name="marketplace-service",   # must match gateway uri("lb://marketplace-service")
            instance_port=settings.APP_PORT,
            instance_host=settings.EUREKA_HOST,
        )
        logger.info("✅ Registered with Eureka as 'marketplace-service' on port %d", settings.APP_PORT)
    except Exception as e:
        logger.warning("⚠️ Eureka registration failed: %s", e)

    yield

    # ── Shutdown: deregister ──
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

    # CORS — allow shell + all MFEs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # shell
            "http://localhost:5174",   # other MFEs
            "http://localhost:5175",   # marketplace MFE
            "http://localhost:5176",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs_router)

    return app


app = create_app()