from typing import Any, Dict

import qbittorrentapi

from torrent_downloader.core.logger import app_logger


def is_vpn_bound(
    client: qbittorrentapi.Client, expected_interface: str = "NordLynx"
) -> bool:
    """
    Verifies that qBittorrent is strictly bound to the VPN network interface.
    This guarantees traffic halts if the VPN drops, bypassing the need for host OS process checks.
    """
    try:
        preferences: Dict[str, Any] = client.app_preferences()
        current_interface: str = str(preferences.get("current_interface_name", ""))

        if current_interface.lower() == expected_interface.lower():
            return True

        app_logger.critical(
            f"SECURITY ALERT: qBittorrent is bound to '{current_interface}', "
            f"but requires '{expected_interface}'. Download rejected."
        )
        return False
    except Exception as e:
        app_logger.error(f"Failed to verify network interface binding: {e}")
        return False
