import warnings
from pathlib import Path
from typing import Any, Dict, List

import qbittorrentapi
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.core.settings_manager import update_environment_variables
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
)
from torrent_downloader.utils.vpn_checker import is_vpn_connected

warnings.filterwarnings("ignore", category=SyntaxWarning)

app: FastAPI = FastAPI(title="Torrent Downloader API")


class DownloadRequest(BaseModel):
    magnet_uri: str
    media_type: str = "unsorted"


class ConfigUpdateRequest(BaseModel):
    search_timeout_seconds: int | None = None
    minimum_seeders: int | None = None
    base_media_dir: str | None = None


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
    if not is_vpn_connected():
        raise HTTPException(status_code=403, detail="VPN is not connected.")

    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    base_path: Path = Path(config.base_media_dir).resolve()
    save_directory: Path = base_path / payload.media_type
    save_directory.mkdir(parents=True, exist_ok=True)

    if config.dry_run:
        return {"status": "success", "message": "Dry run bypassed download."}

    try:
        client.torrents_add(urls=payload.magnet_uri, save_path=str(save_directory))
        return {"status": "success", "message": "Torrent added to queue."}
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


@app.get("/api/v1/settings")
def api_get_settings() -> Dict[str, Any]:
    """Returns the current active configuration state."""
    return {
        "search_timeout_seconds": config.search_timeout_seconds,
        "minimum_seeders": config.minimum_seeders,
        "base_media_dir": config.base_media_dir,
    }


@app.patch("/api/v1/settings")
def api_update_settings(payload: ConfigUpdateRequest) -> Dict[str, str]:
    """Applies configuration updates to the environment file."""
    update_data: Dict[str, Any] = payload.model_dump(exclude_unset=True)

    if update_data:
        update_environment_variables(update_data)
        return {
            "status": "success",
            "message": "Settings updated. Application restart required to apply changes.",
        }

    return {"status": "unchanged", "message": "No valid configuration keys provided."}


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
