"""qBittorrent Web API client: connection, transfer management, and plugin-based search."""

import time
from typing import Any

import PTN
import qbittorrentapi
from qbittorrentapi.exceptions import APIConnectionError

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.transfers import TransferInfo

STATUS_FILTER_ALL: str = "all"
STATUS_FILTER_SEEDING: str = "seeding"
DEFAULT_SPEED_BPS: int = 0
DEFAULT_PROGRESS: float = 0.0
DEFAULT_ETA_SECONDS: int = 0
DEFAULT_HASH: str = ""
DEFAULT_STATE: str = ""
DEFAULT_SAVE_PATH: str = ""

SEARCH_COMPLETION_STATUS: str = "Stopped"
POLL_INTERVAL_SECONDS: float = 1.0
EMPTY_SEEDER_COUNT: int = 0
DEFAULT_SEARCH_ID: int = 0
RES_4K_KEYS: set[str] = {"4k", "2160p"}
RES_1080_KEYS: set[str] = {"1080p"}
RES_720_KEYS: set[str] = {"720p"}


def get_torrent_client() -> qbittorrentapi.Client | None:
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


def get_active_transfers(client: qbittorrentapi.Client) -> list[TransferInfo]:
    """Retrieves current torrent transfers from the client."""
    torrents: Any = client.torrents_info(status_filter=STATUS_FILTER_ALL)
    parsed_transfers: list[TransferInfo] = []

    for torrent in torrents:
        transfer_state: TransferInfo = TransferInfo(
            name=torrent.get("name", ""),
            size=torrent.get("size", DEFAULT_SPEED_BPS),
            progress=torrent.get("progress", DEFAULT_PROGRESS),
            hash=torrent.get("hash", DEFAULT_HASH),
            state=torrent.get("state", DEFAULT_STATE),
            download_speed=torrent.get("dlspeed", DEFAULT_SPEED_BPS),
            upload_speed=torrent.get("upspeed", DEFAULT_SPEED_BPS),
            eta_seconds=torrent.get("eta", DEFAULT_ETA_SECONDS),
            save_path=torrent.get("save_path", DEFAULT_SAVE_PATH),
        )
        parsed_transfers.append(transfer_state)

    return parsed_transfers


def stop_seeding_transfers(client: qbittorrentapi.Client) -> None:
    """Stops torrent transfers from seeding in the client."""
    torrents: Any = client.torrents_info(status_filter=STATUS_FILTER_SEEDING)

    for torrent in torrents:
        client.torrents_pause(torrent.get("hash", ""))
        app_logger.info(f"Succesfully stopped torrent:{torrent.get('name', '')}")


def is_vpn_bound(client: qbittorrentapi.Client, expected_interface: str = "NordLynx") -> bool:
    """
    Verifies that qBittorrent is strictly bound to the VPN network interface.
    This guarantees traffic halts if the VPN drops, bypassing the need for host OS process checks.
    """
    try:
        preferences: dict[str, Any] = client.app_preferences()
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


def execute_plugin_search(client: qbittorrentapi.Client, query: str) -> list[dict[str, Any]]:
    """Runs the qBittorrent plugin search loop and returns raw results.

    Polls until all plugins report completion or the configured timeout is reached,
    at which point any still-running plugins are forcibly stopped before results
    are fetched.
    """
    search_job: dict[str, Any] = client.search_start(
        pattern=query, plugins="all", category="movies"
    )

    search_id: int = search_job.get("id", DEFAULT_SEARCH_ID)
    start_time: float = time.time()

    while True:
        elapsed: float = time.time() - start_time
        if elapsed >= config.search_timeout_seconds:
            app_logger.info(
                f"Search timeout reached ({config.search_timeout_seconds}s). "
                "Terminating hanging plugins."
            )
            client.search_stop(search_id=search_id)
            break

        status: dict[str, Any] = client.search_status(search_id=search_id)
        if status and status[0].get("status") == SEARCH_COMPLETION_STATUS:
            break

        time.sleep(POLL_INTERVAL_SECONDS)

    results: Any = client.search_results(search_id=search_id, limit=0)
    return results.get("results", [])


def search_torrents(client: qbittorrentapi.Client, query: str) -> list[dict[str, Any]]:
    """Returns cached torrent results or executes a new search."""
    cache_key: str = f"torrent_search_{query}"
    cached_results: Any = app_cache.get(cache_key)

    if cached_results is not None:
        app_logger.info(f"Returning cached results for query: '{query}'")
        return cached_results

    app_logger.info(f"Initiating new search for query: '{query}'")
    parsed_results: list[dict[str, Any]] = execute_plugin_search(client, query)

    app_logger.info(f"Search completed. Found {len(parsed_results)} total results.")
    app_cache.set(cache_key, parsed_results, expire=config.cache_expiration_seconds)
    return parsed_results


def filter_and_sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filters by minimum seeders, enforces magnet links, and sorts by seed count descending."""
    filtered: list[dict[str, Any]] = []

    for res in results:
        file_url: str = res.get("fileUrl", "")
        seed_count: int = res.get("nbSeeders", EMPTY_SEEDER_COUNT)

        has_enough_seeds: bool = seed_count >= config.minimum_seeders
        is_magnet_link: bool = file_url.startswith("magnet:?")

        if has_enough_seeds and is_magnet_link:
            filtered.append(res)

    filtered.sort(key=lambda x: x.get("nbSeeders", EMPTY_SEEDER_COUNT), reverse=True)
    return filtered


def group_by_resolution(
    results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Categorizes parsed torrent dictionaries by target resolutions."""
    grouped: dict[str, list[dict[str, Any]]] = {"4K": [], "1080p": [], "720p": []}

    for result in results:
        parsed: dict[str, Any] = PTN.parse(result.get("fileName", ""))
        resolution: str = str(parsed.get("resolution", "")).lower()

        if resolution in RES_4K_KEYS:
            grouped["4K"].append(result)
        elif resolution in RES_1080_KEYS:
            grouped["1080p"].append(result)
        elif resolution in RES_720_KEYS:
            grouped["720p"].append(result)

    return {k: v for k, v in grouped.items() if v}
