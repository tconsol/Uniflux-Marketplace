from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "marketplace"
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
    JOBSPY_DEFAULT_SITES: List[str] = ["indeed", "glassdoor", "google"]

    # Eureka
    EUREKA_SERVER: str = "http://localhost:8761/eureka"
    EUREKA_HOST: str = ""

    # Proxy
    PROXY_URL: Optional[str] = None    # ← added

    class Config:
        env_file = ".env"


settings = Settings()