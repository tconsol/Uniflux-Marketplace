from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MARKETPLACE-SERVICE"
    APP_ENV: str = "development"
    APP_PORT: int = 8085

    # MongoDB
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "market-place"

    # JWT — must match Spring Boot gateway secret
    JWT_SECRET: str = "uniflux-super-secret-key-must-be-32-chars-min"
    JWT_ALGORITHM: str = "HS256"

    # JobSpy
    JOBSPY_MAX_RESULTS: int = 100
    JOBSPY_DEFAULT_SITES: str = "indeed,glassdoor,google"
    PROXY_URL: str = ""
    OPENWEBNINJA_API_KEY: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # Eureka — same pattern as job aggregator
    EUREKA_SERVER: str = "http://localhost:8761/eureka"
    SERVICE_NAME: str = "MARKETPLACE-SERVICE"
    SERVICE_HOST: str = "localhost"
    SERVICE_PORT: int = 8085

    class Config:
        env_file = ".env"


settings = Settings()