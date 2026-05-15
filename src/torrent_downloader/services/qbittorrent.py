import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil
import qbittorrentapi
from qbittorrentapi.exceptions import APIConnectionError

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger

PROCESS_SPIN_UP_DELAY_SECONDS: float = 5.0
STATUS_FILTER_ALL: str = "all"
DEFAULT_SPEED_BPS: int = 0
DEFAULT_PROGRESS: float = 0.0


def is_qbittorrent_running() -> bool:
    """Evaluates active system processes for the target executable."""
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == config.qb_process_name:
            return True
    return False


def ensure_qbittorrent_active() -> None:
    """Verifies process status and initiates the executable if required."""
    if not is_qbittorrent_running():
        app_logger.info("qBittorrent process not found. Initiating executable.")
        subprocess.Popen([config.qb_executable_path], shell=True)
        time.sleep(PROCESS_SPIN_UP_DELAY_SECONDS)


def get_torrent_client() -> Optional[qbittorrentapi.Client]:
    """Instantiates and verifies the qBittorrent client connection."""
    ensure_qbittorrent_active()

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
            "state": torrent.get("state", ""),
            "progress": torrent.get("progress", DEFAULT_PROGRESS),
            "download_speed_bps": torrent.get("dlspeed", DEFAULT_SPEED_BPS),
            "eta_seconds": torrent.get("eta", 0),
        }
        parsed_transfers.append(transfer_state)

    return parsed_transfers
