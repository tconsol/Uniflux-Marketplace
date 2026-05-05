import logging
import py_eureka_client.eureka_client as eureka_client
from app.config import settings

logger = logging.getLogger(__name__)


async def register_with_eureka():
    """Register marketplace service with Eureka on startup."""
    try:
        await eureka_client.init_async(
            eureka_server=settings.EUREKA_SERVER,
            app_name=settings.APP_NAME,
            instance_port=settings.APP_PORT,
            instance_host=settings.SERVICE_HOST,
            renewal_interval_in_secs=30,
            duration_in_secs=90,
            metadata={
                "version": "1.0.0",
                "env": settings.APP_ENV,
                "service": "marketplace",
                "description": "Job aggregator & marketplace service",
            }
        )
        logger.info(
            f"✅ Registered '{settings.APP_NAME}' with Eureka at {settings.EUREKA_SERVER}"
        )
    except Exception as e:
        logger.error(f"❌ Eureka registration failed: {e}")


async def deregister_from_eureka():
    """Deregister marketplace service from Eureka on shutdown."""
    try:
        await eureka_client.stop_async()
        logger.info(f"✅ Deregistered '{settings.APP_NAME}' from Eureka")
    except Exception as e:
        logger.error(f"❌ Eureka deregistration failed: {e}")