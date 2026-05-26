"""Transfers router: download submission, transfer listing, and seeding control."""

import qbittorrentapi
from fastapi import APIRouter, HTTPException
from fastapi import status as fastapi_status
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.constants import TAG_TRANSFERS
from torrent_downloader.schemas.downloads import DownloadRequest, DownloadResponse
from torrent_downloader.schemas.transfers import TransferInfoResponse
from torrent_downloader.services.qbittorrent import (
    get_active_transfers,
    get_torrent_client,
    is_vpn_bound,
    stop_seeding_transfers,
)

router = APIRouter(tags=[TAG_TRANSFERS])


@router.post(
    "/download",
    response_model=DownloadResponse,
    status_code=fastapi_status.HTTP_202_ACCEPTED,
    summary="Submits a selected magnet URI to the qBittorrent daemon.",
)
def api_trigger_download(payload: DownloadRequest) -> DownloadResponse:
    """Submit a magnet URI to the qBittorrent daemon, enforcing VPN binding beforehand.

    Raises:
        HTTPException: 503 if the qBittorrent client is unreachable.
        HTTPException: 403 if qBittorrent is not bound to the required VPN interface.
    """
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    if not is_vpn_bound(client):
        raise HTTPException(
            status_code=403,
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
)
def api_get_transfers() -> TransferInfoResponse:
    """Return a snapshot of all active qBittorrent transfers."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    try:
        return TransferInfoResponse(
            status="success", message="", data=get_active_transfers(client)
        )
    except Exception as e:
        return TransferInfoResponse(status="error", message=str(e), data=[])


@router.post(
    "/transfers/stop-seeding",
    response_model=DownloadResponse,
    status_code=fastapi_status.HTTP_202_ACCEPTED,
    summary="Changes the state of all seeding qBittorrent transfers to stopped.",
)
def api_stop_seeding_transfers() -> DownloadResponse:
    """Pause all torrents currently in the seeding state."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    try:
        stop_seeding_transfers(client)
        return DownloadResponse(status="success", message="All seeding transfers stopped.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
