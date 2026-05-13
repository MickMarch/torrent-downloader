from typing import Optional

import qbittorrentapi
from qbittorrentapi.exceptions import APIConnectionError

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger


def get_torrent_client() -> Optional[qbittorrentapi.Client]:
    """Instantiates and verifies the qBittorrent client connection."""
    client: qbittorrentapi.Client = qbittorrentapi.Client(
        host=f"{config.qb_host}:{config.qb_port}",
        EXTRA_HEADERS={"Authorization": f"Bearer {config.qb_api_key}"},
    )

    try:
        client.app_web_api_version()
        app_logger.info(
            f"Successfully connected to qBittorrent Web UI at {config.qb_host}:{config.qb_port}"
        )
        return client
    except APIConnectionError as error:
        app_logger.error(
            f"Failed to connect to qBittorrent Web UI: {error}. Verify application status and port configuration."
        )
        return None
