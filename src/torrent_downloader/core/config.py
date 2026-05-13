from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration parameters."""

    model_config: SettingsConfigDict = SettingsConfigDict(env_file=".env")

    qb_host: str = Field(default="127.0.0.1")
    qb_port: int = Field(default=8080)
    qb_api_key: str = Field(...)

    base_media_dir: str = Field(default="/downloads/media")
    target_language: str = Field(default="en")
    minimum_seeders: int = Field(default=10)
    tmdb_api_key: str = Field(...)

    dry_run: bool = Field(default=True)
    search_timeout_seconds: int = Field(default=15)


config: AppConfig = AppConfig()
