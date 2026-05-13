import time
import warnings
from typing import Any, Dict, List

import PTN
import qbittorrentapi

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger

warnings.filterwarnings("ignore", category=SyntaxWarning)

SEARCH_COMPLETION_STATUS: str = "Stopped"
POLL_INTERVAL_SECONDS: float = 1.0
EMPTY_SEEDER_COUNT: int = 0
RES_4K_KEYS: set[str] = {"4k", "2160p"}
RES_1080_KEYS: set[str] = {"1080p"}
RES_720_KEYS: set[str] = {"720p"}


def search_torrents(client: qbittorrentapi.Client, query: str) -> List[Dict[str, Any]]:
    """Executes a search job and returns results, adhering to the configured timeout."""
    app_logger.info(f"Initiating search for query: '{query}'")

    search_job: Dict[str, Any] = client.search_start(
        pattern=query, plugins="all", category="movies"
    )

    search_id: int = search_job.get("id")
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
    parsed_results: List[Dict[str, Any]] = results.get("results", [])

    app_logger.info(f"Search completed. Found {len(parsed_results)} total results.")
    return parsed_results


def filter_and_sort_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters by minimum seeders, enforces magnet links, and sorts by seed count descending."""
    filtered: List[Dict[str, Any]] = []

    for res in results:
        file_url: str = res.get("fileUrl", "")
        seed_count: int = res.get("nbSeeders", EMPTY_SEEDER_COUNT)

        has_enough_seeds: bool = seed_count >= config.minimum_seeders
        # Enforce that the result is a direct magnet URI
        is_magnet_link: bool = file_url.startswith("magnet:?")

        if has_enough_seeds and is_magnet_link:
            filtered.append(res)

    filtered.sort(key=lambda x: x.get("nbSeeders", EMPTY_SEEDER_COUNT), reverse=True)
    return filtered


def group_by_resolution(
    results: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Parses torrent filenames and categorizes them by target resolutions."""
    grouped: Dict[str, List[Dict[str, Any]]] = {"4K": [], "1080p": [], "720p": []}

    for result in results:
        # Changed PTN to ptn here
        parsed: Dict[str, Any] = PTN.parse(result.get("fileName", ""))
        resolution: str = str(parsed.get("resolution", "")).lower()

        if resolution in RES_4K_KEYS:
            grouped["4K"].append(result)
        elif resolution in RES_1080_KEYS:
            grouped["1080p"].append(result)
        elif resolution in RES_720_KEYS:
            grouped["720p"].append(result)

    return {k: v for k, v in grouped.items() if v}
