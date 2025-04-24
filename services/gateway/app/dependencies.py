from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict

class Settings(BaseSettings):
    environment: str = Field("dev", env="ENV")
    log_level: str    = Field("info", env="LOG_LEVEL")
    redis_url: str    = Field("redis://redis:6379", env="REDIS_URL")

    # load from .env and ignore any extra keys
    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
