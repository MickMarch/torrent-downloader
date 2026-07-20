"""Transfers router: download submission, transfer listing, and seeding control."""

import re

import qbittorrentapi
from fastapi import APIRouter, Request
from fastapi import status as fastapi_status
from medialab_contracts import MediaType
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config
from torrent_downloader.core.constants import TAG_TRANSFERS
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_DEFAULT, limiter
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.downloads import DownloadRequest, DownloadResponse
from torrent_downloader.schemas.errors import ErrorResponse
from torrent_downloader.schemas.transfers import TransferHashInfo, TransferInfoResponse
from torrent_downloader.services.qbittorrent import (
    MAGNET_URL_PREFIX,
    get_active_transfers,
    get_torrent_client,
    is_vpn_bound,
    stop_seeding_transfers,
)

router = APIRouter(tags=[TAG_TRANSFERS])

MAGNET_HASH_PATTERN = re.compile(r"xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})")
MEDIA_TYPE_CACHE_PREFIX = "media_type:"
MEDIA_TYPE_SUBDIRS = {MediaType.MOVIE: "Movies", MediaType.SHOW: "Shows"}


_QB_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Missing/invalid API key or VPN not bound."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    503: {"model": ErrorResponse, "description": "qBittorrent client unavailable."},
}


def _extract_hash(magnet_uri: str) -> str | None:
    """Extracts and lowercases the BTIH hash from a magnet URI."""
    match = MAGNET_HASH_PATTERN.search(magnet_uri)
    return match.group(1).lower() if match else None


def _snapshot_hashes(client: qbittorrentapi.Client) -> set[str]:
    """Returns the set of info-hashes qBittorrent currently tracks (lowercased)."""
    return {str(t.get("hash", "")).lower() for t in client.torrents_info(status_filter="all")}


def _resolve_added_hash(client: qbittorrentapi.Client, before: set[str]) -> str | None:
    """Identifies the just-added torrent's hash by diffing against a pre-add snapshot.

    Deterministic under concurrent adds and equal to qBittorrent's own computed
    info-hash (so it matches the completion webhook's ``%I``). Returns ``None``
    when the diff is empty (qB deduped an already-present torrent, or the add
    failed) or ambiguous (more than one new hash), leaving the completion webhook
    to backfill.
    """
    new_hashes = _snapshot_hashes(client) - before
    if len(new_hashes) == 1:
        return next(iter(new_hashes))
    return None


def _resolve_host_path(media_type: MediaType) -> str:
    """Builds the host-side save path qBittorrent runs on. The container never
    sees this path on disk - it exists only on the host filesystem."""
    if config.media_host_path is None:
        raise AppException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            detail="MEDIA_HOST_PATH is not configured.",
        )
    base = config.media_host_path.rstrip("\\/")
    return f"{base}\\{MEDIA_TYPE_SUBDIRS[media_type]}"


@router.post(
    "/download",
    response_model=DownloadResponse,
    status_code=fastapi_status.HTTP_202_ACCEPTED,
    summary="Submits a selected torrent source (magnet or .torrent URL) to qBittorrent.",
    responses=_QB_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def api_trigger_download(request: Request, payload: DownloadRequest) -> DownloadResponse:
    """Submit a torrent source (magnet or .torrent URL), enforcing VPN binding beforehand."""
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

    host_path = _resolve_host_path(payload.media_type)

    if payload.dry_run:
        return DownloadResponse(
            status="success",
            message=f"Dry run bypassed download. Target: {host_path}",
        )

    is_magnet = payload.source_url.startswith(MAGNET_URL_PREFIX)
    # For a magnet the hash is in the URI; for a .torrent URL it is only known
    # after qBittorrent computes it, so snapshot the tracked hashes first and
    # diff after the add.
    pre_add_hashes = set() if is_magnet else _snapshot_hashes(client)

    try:
        client.torrents_add(urls=payload.source_url, save_path=host_path)
    except Conflict409Error:
        return DownloadResponse(
            status="conflict",
            message="Torrent already exists in transfer list.",
        )

    torrent_hash = (
        _extract_hash(payload.source_url)
        if is_magnet
        else _resolve_added_hash(client, pre_add_hashes)
    )

    if torrent_hash:
        app_cache.set(
            f"{MEDIA_TYPE_CACHE_PREFIX}{torrent_hash}",
            {
                "media_type": payload.media_type,
                "host_path": host_path,
                "tmdb_id": payload.tmdb_id,
            },
        )
    else:
        app_logger.warning(
            "Could not resolve BTIH hash for source; media_type metadata not cached. "
            "The completion webhook will backfill it. source_url=%r",
            payload.source_url,
        )

    return DownloadResponse(
        status="success",
        message=f"Torrent added to queue. Save path: {host_path}",
        torrent_hash=torrent_hash,
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

    return TransferInfoResponse(status="success", message="", data=get_active_transfers(client))


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


@router.get(
    "/transfers/{torrent_hash}/info",
    response_model=TransferHashInfo,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns cached media_type and host path metadata for a completed download.",
    responses={
        404: {"model": ErrorResponse, "description": "No cached metadata for this hash."},
        **_QB_ERROR_RESPONSES,
    },
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def api_get_transfer_info(request: Request, torrent_hash: str) -> TransferHashInfo:
    """Look up the media_type and host path stored at download submission time."""
    cached = app_cache.get(f"{MEDIA_TYPE_CACHE_PREFIX}{torrent_hash.lower()}")
    if cached is None:
        raise AppException(
            status_code=fastapi_status.HTTP_404_NOT_FOUND,
            code=ErrorCode.TRANSFER_NOT_FOUND,
            detail=f"No cached metadata found for hash: {torrent_hash}",
        )

    return TransferHashInfo(
        media_type=cached["media_type"],
        host_path=cached["host_path"],
        tmdb_id=cached["tmdb_id"],
    )
