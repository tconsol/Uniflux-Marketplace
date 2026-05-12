from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "marketplace-service"
    APP_ENV: str = "development"
    APP_PORT: int = 8085

    # Mongo
    MONGODB_URI: str = ""
    MONGODB_DB_NAME: str = "marketplace_dev"

    # JWT
    JWT_SECRET: str = "uniflux-super-secret-key-must-be-32-chars-min"
    JWT_ALGORITHM: str = "HS256"

    # JobSpy defaults
    JOBSPY_MAX_RESULTS: int = 100
    JOBSPY_DEFAULT_SITES: str = "indeed,glassdoor,google"  # always a plain string

    # Eureka
    EUREKA_SERVER: str = "http://localhost:8761/eureka"
    EUREKA_HOST: str = ""

    FRONTEND_URL: str = "http://localhost:5173"

    # Proxy
    PROXY_URL: Optional[str] = None

    @property
    def jobspy_sites(self) -> List[str]:
        return [s.strip() for s in self.JOBSPY_DEFAULT_SITES.split(",")]

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()