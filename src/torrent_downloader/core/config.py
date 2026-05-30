"""Application configuration loaded from environment variables and an optional .env file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration parameters."""

    model_config: SettingsConfigDict = SettingsConfigDict(env_file=".env")

    qb_host: str = Field(default="127.0.0.1")
    qb_port: int = Field(default=8080)
    qb_api_key: str | None = Field(default=None)

    target_language: str = Field(default="en")
    minimum_seeders: int = Field(default=10)
    tmdb_api_key: str | None = Field(default=None)

    search_timeout_seconds: int = Field(default=15)

    cache_directory: str = Field(default=".cache")
    cache_expiration_seconds: int = Field(default=3600)

    api_key: str | None = Field(default=None)
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)


config: AppConfig = AppConfig()
