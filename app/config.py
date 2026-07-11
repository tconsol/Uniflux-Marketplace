from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MARKETPLACE-SERVICE"
    APP_ENV: str = "development"
    APP_PORT: int = 8085

    # MongoDB
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "market-place"

    # JWT - must match the gateway/shared secret. Required, no default: a missing
    # env var must fail startup rather than silently signing/verifying tokens with a
    # guessable value that's public in source history.
    JWT_SECRET: str
    # Comma-separated list of accepted HMAC algorithms. The token issuer signs with
    # HS512; HS256 is kept for backward compatibility. See auth_middleware for why both
    # are always accepted regardless of this value.
    JWT_ALGORITHM: str = "HS256,HS512"

    # JobSpy
    JOBSPY_MAX_RESULTS: int = 100
    JOBSPY_DEFAULT_SITES: str = "indeed,glassdoor,google"
    PROXY_URL: str = ""
    OPENWEBNINJA_API_KEY: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # Eureka — same pattern as job aggregator
    EUREKA_SERVER: str = "http://localhost:8761/eureka"
    SERVICE_NAME: str = "marketplace"
    SERVICE_HOST: str = "localhost"
    SERVICE_PORT: int = 8085

    class Config:
        env_file = ".env"


settings = Settings()