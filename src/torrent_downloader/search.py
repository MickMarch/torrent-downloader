import time
from typing import Any, Dict, List

import PTN
import qbittorrentapi

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger

SEARCH_COMPLETION_STATUS: str = "Stopped"
POLL_INTERVAL_SECONDS: float = 1.0
EMPTY_SEEDER_COUNT: int = 0
DEFAULT_SEARCH_ID: int = 0
RES_4K_KEYS: set[str] = {"4k", "2160p"}
RES_1080_KEYS: set[str] = {"1080p"}
RES_720_KEYS: set[str] = {"720p"}


def execute_plugin_search(
    client: qbittorrentapi.Client, query: str
) -> List[Dict[str, Any]]:
    """Internal function to handle the search loop execution."""
    search_job: Dict[str, Any] = client.search_start(
        pattern=query, plugins="all", category="movies"
    )

    search_id: int = search_job.get("id", DEFAULT_SEARCH_ID)
    start_time: float = time.time()

    while True:
        elapsed: float = time.time() - start_time
        if elapsed >= config.search_timeout_seconds:
            app_logger.info(
                f"Search timeout reached ({config.search_timeout_seconds}s). Terminating hanging plugins."
            )
            client.search_stop(search_id=search_id)
            break

        status: Dict[str, Any] = client.search_status(search_id=search_id)
        if status and status[0].get("status") == SEARCH_COMPLETION_STATUS:
            break

        time.sleep(POLL_INTERVAL_SECONDS)

    results: Any = client.search_results(search_id=search_id, limit=0)
    return results.get("results", [])


def search_torrents(client: qbittorrentapi.Client, query: str) -> List[Dict[str, Any]]:
    """Returns cached torrent results or executes a new search."""
    cache_key: str = f"torrent_search_{query}"
    cached_results: Any = app_cache.get(cache_key)

    if cached_results is not None:
        app_logger.info(f"Returning cached results for query: '{query}'")
        return cached_results

    app_logger.info(f"Initiating new search for query: '{query}'")
    parsed_results: List[Dict[str, Any]] = execute_plugin_search(client, query)

    app_logger.info(f"Search completed. Found {len(parsed_results)} total results.")
    app_cache.set(cache_key, parsed_results, expire=config.cache_expiration_seconds)
    return parsed_results


def filter_and_sort_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters by minimum seeders, enforces magnet links, and sorts by seed count descending."""
    filtered: List[Dict[str, Any]] = []

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
    results: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Categorizes parsed torrent dictionaries by target resolutions."""
    grouped: Dict[str, List[Dict[str, Any]]] = {"4K": [], "1080p": [], "720p": []}

    for result in results:
        parsed: Dict[str, Any] = PTN.parse(result.get("fileName", ""))
        resolution: str = str(parsed.get("resolution", "")).lower()

        if resolution in RES_4K_KEYS:
            grouped["4K"].append(result)
        elif resolution in RES_1080_KEYS:
            grouped["1080p"].append(result)
        elif resolution in RES_720_KEYS:
            grouped["720p"].append(result)

    return {k: v for k, v in grouped.items() if v}
