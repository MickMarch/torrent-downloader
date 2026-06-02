"""Transfers router: download submission, transfer listing, and seeding control."""

import qbittorrentapi
from fastapi import APIRouter, Request
from fastapi import status as fastapi_status
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.constants import TAG_TRANSFERS
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_DEFAULT, limiter
from torrent_downloader.schemas.errors import ErrorResponse
from torrent_downloader.schemas.downloads import DownloadRequest, DownloadResponse
from torrent_downloader.schemas.transfers import TransferInfoResponse
from torrent_downloader.services.qbittorrent import (
    get_active_transfers,
    get_torrent_client,
    is_vpn_bound,
    stop_seeding_transfers,
)

router = APIRouter(tags=[TAG_TRANSFERS])


_QB_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Missing/invalid API key or VPN not bound."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    503: {"model": ErrorResponse, "description": "qBittorrent client unavailable."},
}


@router.post(
    "/download",
    response_model=DownloadResponse,
    status_code=fastapi_status.HTTP_202_ACCEPTED,
    summary="Submits a selected magnet URI to the qBittorrent daemon.",
    responses=_QB_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def api_trigger_download(request: Request, payload: DownloadRequest) -> DownloadResponse:
    """Submit a magnet URI to the qBittorrent daemon, enforcing VPN binding beforehand."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise AppException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.QB_UNAVAILABLE,
            detail="qBittorrent client unavailable.",
        )

    if not is_vpn_bound(client):
        raise AppException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            code=ErrorCode.VPN_NOT_BOUND,
            detail="qBittorrent is not bound to the required VPN interface.",
        )

    if payload.dry_run:
        return DownloadResponse(
            status="success",
            message=f"Dry run bypassed download. Target: {payload.save_path}",
        )

    try:
        client.torrents_add(urls=payload.magnet_uri, save_path=payload.save_path)
        return DownloadResponse(
            status="success",
            message=f"Torrent added to queue. Save path: {payload.save_path}",
        )
    except Conflict409Error:
        return DownloadResponse(
            status="conflict",
            message="Torrent already exists in transfer list.",
        )


@router.get(
    "/transfers",
    response_model=TransferInfoResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns the current state of all qBittorrent transfers.",
    responses=_QB_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def api_get_transfers(request: Request) -> TransferInfoResponse:
    """Return a snapshot of all active qBittorrent transfers."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise AppException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.QB_UNAVAILABLE,
            detail="qBittorrent client unavailable.",
        )

    return TransferInfoResponse(
        status="success", message="", data=get_active_transfers(client)
    )


@router.post(
    "/transfers/stop-seeding",
    response_model=DownloadResponse,
    status_code=fastapi_status.HTTP_202_ACCEPTED,
    summary="Changes the state of all seeding qBittorrent transfers to stopped.",
    responses=_QB_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def api_stop_seeding_transfers(request: Request) -> DownloadResponse:
    """Pause all torrents currently in the seeding state."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise AppException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.QB_UNAVAILABLE,
            detail="qBittorrent client unavailable.",
        )

    stop_seeding_transfers(client)
    return DownloadResponse(status="success", message="All seeding transfers stopped.")
