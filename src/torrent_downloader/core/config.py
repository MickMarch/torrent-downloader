"""Application configuration loaded from environment variables and an optional .env file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from torrent_downloader.services.language import LanguageFilter

VPN_INTERFACE_SEPARATOR: str = ","
# The WireGuard tunnel interface inside a gluetun network namespace. A host
# install overrides this with the adapter name qBittorrent is bound to.
DEFAULT_VPN_INTERFACES: str = "tun0"

SECONDS_PER_HOUR: int = 3600
HOURS_PER_DAY: int = 24
DAYS_PER_WEEK: int = 7
SECONDS_PER_DAY: int = SECONDS_PER_HOUR * HOURS_PER_DAY
DISCOVER_CACHE_SECONDS_DEFAULT: int = SECONDS_PER_DAY
DISCOVER_CACHE_SECONDS_MIN: int = SECONDS_PER_HOUR
DISCOVER_CACHE_SECONDS_MAX: int = SECONDS_PER_DAY * DAYS_PER_WEEK


class AppConfig(BaseSettings):
    """Application configuration parameters."""

    model_config = SettingsConfigDict(env_file=".env")

    qb_host: str = Field(default="127.0.0.1")
    qb_port: int = Field(default=8080)
    qb_api_key: str | None = Field(default=None)

    target_language: str = Field(default="en")
    # lenient: drop explicitly foreign single-language releases; strict: also
    # drop untagged ones; off: show tags only. See services/language.py.
    audio_language_filter: LanguageFilter = Field(default=LanguageFilter.LENIENT)
    minimum_seeders: int = Field(default=10)
    tmdb_api_key: str | None = Field(default=None)

    search_timeout_seconds: int = Field(default=15)
    # Plugin searches run in parallel up to this many at once (a scoped search
    # with an alternate title can need four patterns).
    search_concurrency: int = Field(default=4, ge=1)

    cache_directory: str = Field(default=".cache")
    cache_expiration_seconds: int = Field(default=3600)
    # Trending, discover-by-genre and genre lists; read at each cache write.
    discover_cache_seconds: int = Field(default=DISCOVER_CACHE_SECONDS_DEFAULT)
    # Runtime setting overrides (see core/settings.py); lives on the cache volume.
    settings_path: str = Field(default=".cache/settings.json")

    api_key: str | None = Field(default=None)
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # In-container path of the media root, the same bind mount qBittorrent and
    # the orchestrator see. save_path values handed to qBittorrent are built
    # under it with "/" separators.
    media_mount_path: str | None = Field(default=None)

    # Comma-separated rather than list[str]: pydantic-settings JSON-parses complex
    # types in the env source before validators run, so a plain comma string on a
    # list field raises SettingsError. A str field also round-trips correctly
    # through the runtime settings store.
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
