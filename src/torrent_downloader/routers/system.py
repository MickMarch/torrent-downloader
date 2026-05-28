"""System router: health check and operational status endpoints."""

import time

import qbittorrentapi
from fastapi import APIRouter
from fastapi import status as fastapi_status

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.constants import API_START_TIME, TAG_SYSTEM
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.system import CacheClearResponse, HealthResponse
from torrent_downloader.services.qbittorrent import get_torrent_client, is_vpn_bound

router = APIRouter(tags=[TAG_SYSTEM])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns the current operational status and uptime of the API.",
)
def api_health_check() -> HealthResponse:
    """Return current uptime and VPN binding status for liveness monitoring."""
    uptime_seconds: float = time.time() - API_START_TIME

    vpn_status: bool = False
    client: qbittorrentapi.Client | None = get_torrent_client()
    if client:
        vpn_status = is_vpn_bound(client)

    return HealthResponse(
        status="online",
        uptime_seconds=round(uptime_seconds, 2),
        vpn_interface_bound=vpn_status,
    )


@router.delete(
    "/cache",
    response_model=CacheClearResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Clears all cached data.",
)
def clear_cache() -> CacheClearResponse:
    """Evict all entries from the application cache."""
    app_cache.clear()
    app_logger.info("Application cache cleared.")
    return CacheClearResponse(cleared=True, message="Cache cleared successfully.")
