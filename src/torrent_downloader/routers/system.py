"""System router: health check and operational status endpoints."""

import time

import qbittorrentapi
from fastapi import APIRouter
from fastapi import status as fastapi_status

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.constants import API_START_TIME, TAG_SYSTEM
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.system import CacheClearResponse, DiskUsageResponse, HealthResponse
from torrent_downloader.services.qbittorrent import get_torrent_client, is_vpn_bound
from torrent_downloader.services.storage import get_disk_usage

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


@router.get(
    "/storage",
    response_model=DiskUsageResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns disk usage for the given save path.",
)
def get_storage_info(path: str) -> DiskUsageResponse:
    """Return total, used, and free disk space for the specified save path."""
    try:
        usage = get_disk_usage(path)
    except FileNotFoundError:
        raise AppException(
            status_code=fastapi_status.HTTP_404_NOT_FOUND,
            code=ErrorCode.PATH_NOT_FOUND,
            detail=f"Path not found: {path}",
        )
    except PermissionError:
        raise AppException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            code=ErrorCode.PERMISSION_DENIED,
            detail=f"Permission denied: {path}",
        )
    except OSError:
        raise AppException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            detail="Disk usage check failed.",
        )
    return DiskUsageResponse(path=path, **usage)


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
