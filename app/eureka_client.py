import py_eureka_client.eureka_client as eureka_client
from app.config import settings
import logging

logger = logging.getLogger(__name__)


async def register_with_eureka():
    try:
        await eureka_client.init_async(
            eureka_server=settings.EUREKA_SERVER,
            app_name=settings.SERVICE_NAME,
            instance_port=settings.SERVICE_PORT,
            instance_host=settings.SERVICE_HOST,
            renewal_interval_in_secs=30,
            duration_in_secs=90,
            metadata={
                "version": "0.1.0",
                "env": settings.APP_ENV,
            }
        )
        logger.info("✅ Registered '%s' with Eureka at %s", settings.SERVICE_NAME, settings.EUREKA_SERVER)
    except Exception as e:
        logger.error("❌ Eureka registration failed: %s", e)


async def deregister_from_eureka():
    try:
        await eureka_client.stop_async()
        logger.info("✅ Deregistered '%s' from Eureka", settings.SERVICE_NAME)
    except Exception as e:
        logger.error("❌ Eureka deregistration failed: %s", e)