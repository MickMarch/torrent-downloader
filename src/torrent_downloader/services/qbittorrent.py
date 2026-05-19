from typing import Any, Dict, List, Optional

import qbittorrentapi
from qbittorrentapi.exceptions import APIConnectionError

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger

STATUS_FILTER_ALL: str = "all"
STATUS_FILTER_SEEDING: str = "seeding"
DEFAULT_SPEED_BPS: int = 0
DEFAULT_PROGRESS: float = 0.0


def get_torrent_client() -> Optional[qbittorrentapi.Client]:
    """Instantiates and verifies the qBittorrent client connection."""
    client: qbittorrentapi.Client = qbittorrentapi.Client(
        host=f"{config.qb_host}:{config.qb_port}",
        EXTRA_HEADERS={"Authorization": f"Bearer {config.qb_api_key}"},
    )

    try:
        client.app_web_api_version()
        return client
    except APIConnectionError as error:
        app_logger.error(f"Failed to connect to qBittorrent Web UI: {error}")
        return None


def get_active_transfers(client: qbittorrentapi.Client) -> List[Dict[str, Any]]:
    """Retrieves current torrent transfers from the client."""
    torrents: Any = client.torrents_info(status_filter=STATUS_FILTER_ALL)
    parsed_transfers: List[Dict[str, Any]] = []

    for torrent in torrents:
        transfer_state: Dict[str, Any] = {
            "name": torrent.get("name", ""),
            "hash": torrent.get("hash", ""),
            "state": torrent.get("state", ""),
            "progress": torrent.get("progress", DEFAULT_PROGRESS),
            "download_speed_bps": torrent.get("dlspeed", DEFAULT_SPEED_BPS),
            "eta_seconds": torrent.get("eta", 0),
        }
        parsed_transfers.append(transfer_state)

    return parsed_transfers


def stop_seeding_transfers(client: qbittorrentapi.Client) -> None:
    """Stops torrent transfers from seeding in the client."""
    torrents: Any = client.torrents_info(status_filter=STATUS_FILTER_SEEDING)

    for torrent in torrents:
        client.torrents_pause(torrent.get("hash", ""))
        app_logger.info(f"Succesfully stopped torrent:{torrent.get('name', '')}")
