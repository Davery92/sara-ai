from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    environment: str = Field("dev", env="ENV")
    log_level: str = Field("info", env="LOG_LEVEL")
    redis_url: str = Field("redis://redis:6379", env="REDIS_URL")

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:       # FastAPI’s Dependency
    return Settings()
