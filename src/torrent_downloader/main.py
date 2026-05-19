import time
from pathlib import Path
from typing import Any, Dict, List

import qbittorrentapi
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.metadata import (
    extract_media_type,
    extract_title,
    extract_year,
    search_tmdb_multi,
)
from torrent_downloader.search import (
    filter_and_sort_results,
    group_by_resolution,
    search_torrents,
)
from torrent_downloader.services.qbittorrent import (
    get_active_transfers,
    get_torrent_client,
    stop_seeding_transfers,
)
from torrent_downloader.utils.vpn_checker import is_vpn_bound

API_START_TIME: float = time.time()

app: FastAPI = FastAPI(title="Torrent Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    magnet_uri: str
    media_type: str = "unsorted"
    dry_run: bool = False


@app.get("/api/v1/health")
def api_health_check() -> Dict[str, Any]:
    """Returns the current operational status and uptime of the API."""
    uptime_seconds: float = time.time() - API_START_TIME

    # We pass the VPN status check directly into the health payload
    vpn_status: bool = False
    client: qbittorrentapi.Client | None = get_torrent_client()
    if client:
        vpn_status = is_vpn_bound(client)

    return {
        "status": "online",
        "uptime_seconds": round(uptime_seconds, 2),
        "vpn_interface_bound": vpn_status,
    }


@app.get("/api/v1/search/tmdb")
def api_search_tmdb(query: str) -> List[Dict[str, Any]]:
    """Returns formatted TMDB metadata for dispatcher selection."""
    raw_results: List[Dict[str, Any]] = search_tmdb_multi(query)
    formatted_results: List[Dict[str, Any]] = []

    for item in raw_results:
        formatted_results.append(
            {
                "title": extract_title(item),
                "year": extract_year(item),
                "media_type": extract_media_type(item),
                "original_data": item,
            }
        )
    return formatted_results


@app.get("/api/v1/search/torrents")
def api_search_torrents(query: str) -> Dict[str, List[Dict[str, Any]]]:
    """Returns torrents grouped by resolution."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    raw_results: List[Dict[str, Any]] = search_torrents(client, query)
    processed_results: List[Dict[str, Any]] = filter_and_sort_results(raw_results)

    return group_by_resolution(processed_results)


@app.post("/api/v1/download")
def api_trigger_download(payload: DownloadRequest) -> Dict[str, str]:
    """Submits a selected magnet URI to the qBittorrent daemon."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    if not is_vpn_bound(client):
        raise HTTPException(
            status_code=403,
            detail="qBittorrent is not bound to the required VPN interface.",
        )

    # Construct the string explicitly to avoid Linux/Windows pathlib conflicts in Docker
    base_dir: Path = Path(config.base_media_dir)
    save_directory: Path = base_dir / payload.media_type
    save_directory.mkdir(parents=True, exist_ok=True)

    if payload.dry_run:
        return {
            "status": "success",
            "message": f"Dry run bypassed download. Target: {save_directory}",
        }

    try:
        client.torrents_add(urls=payload.magnet_uri, save_path=save_directory)
        return {
            "status": "success",
            "message": f"Torrent added to queue. Save path: {save_directory}",
        }
    except Conflict409Error:
        return {
            "status": "conflict",
            "message": "Torrent already exists in transfer list.",
        }


@app.get("/api/v1/transfers")
def api_get_transfers() -> List[Dict[str, Any]]:
    """Returns the current state of all qBittorrent transfers."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    return get_active_transfers(client)


@app.post(
    "/api/v1/transfers/stop-seeding",
    response_model=Dict[str, str],
    status_code=200,
    summary="Changes the state of all seeding qBittorrent transfers to stopped",
    tags=["Transfer Management"],
)
def api_stop_seeding_transfers() -> Dict[str, str]:
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    try:
        stop_seeding_transfers(client)
        return {"status": "success", "message": "All seeding transfers stopped."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main() -> None:
    """Starts the uvicorn ASGI server for production."""
    app_logger.info("Starting Torrent Downloader API Server...")
    uvicorn.run(
        "torrent_downloader.main:app", host=config.api_host, port=config.api_port
    )


def dev() -> None:
    """Starts the uvicorn ASGI server with hot-reloading enabled."""
    app_logger.info("Starting Torrent Downloader API Server in DEV MODE...")
    uvicorn.run(
        "torrent_downloader.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
