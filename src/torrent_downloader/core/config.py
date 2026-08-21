"""Application configuration loaded from environment variables and an optional .env file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

VPN_INTERFACE_SEPARATOR: str = ","
DEFAULT_VPN_INTERFACES: str = "NordLynx"


class AppConfig(BaseSettings):
    """Application configuration parameters."""

    model_config = SettingsConfigDict(env_file=".env")

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

    media_host_path: str | None = Field(default=None)

    # Comma-separated rather than list[str]: pydantic-settings JSON-parses complex
    # types in the env source before validators run, so a plain comma string on a
    # list field raises SettingsError. A str field also round-trips correctly
    # through settings_manager.update_environment_variables.
    vpn_interfaces: str = Field(default=DEFAULT_VPN_INTERFACES)

    @property
    def vpn_interface_allowlist(self) -> tuple[str, ...]:
        """Accepted VPN interface names. Empty means deny every download."""
        return tuple(
            name.strip()
            for name in self.vpn_interfaces.split(VPN_INTERFACE_SEPARATOR)
            if name.strip()
        )


config: AppConfig = AppConfig()
