import sys
from pathlib import Path
from typing import Any, Dict, List

import qbittorrentapi
from qbittorrentapi.exceptions import Conflict409Error

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.metadata import extract_title, extract_year, search_tmdb_multi
from torrent_downloader.search import (
    filter_and_sort_results,
    group_by_resolution,
    search_torrents,
)
from torrent_downloader.services.qbittorrent import get_torrent_client
from torrent_downloader.utils.vpn_checker import is_vpn_connected

MAX_RESULTS_DISPLAY: int = 5
EXIT_FAILURE: int = 1


def select_from_list(prompt: str, max_index: int) -> int:
    """Retrieves a valid integer index from standard input."""
    while True:
        selection: str = input(prompt)
        if selection.isdigit():
            index: int = int(selection)
            if 0 <= index <= max_index:
                return index
        print("Invalid selection. Try again.")


def main() -> None:
    if not is_vpn_connected():
        app_logger.critical("VPN is not connected. Aborting execution.")
        sys.exit(EXIT_FAILURE)

    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        app_logger.critical(
            "Could not establish connection to torrent client. Aborting execution."
        )
        sys.exit(EXIT_FAILURE)

    try:
        search_query: str = input("Enter movie or show title: ")

        tmdb_results: List[Dict[str, Any]] = search_tmdb_multi(search_query)
        if not tmdb_results:
            app_logger.warning("No matches found on TMDB.")
            return

        print("\nTMDB Results:")
        for idx, item in enumerate(tmdb_results[:MAX_RESULTS_DISPLAY]):
            title: str = extract_title(item)
            year: str = extract_year(item)
            media_type: str = item.get("media_type", "unknown").upper()
            print(f"[{idx}] {title} ({year}) - {media_type}")

        target_tmdb_index: int = select_from_list(
            "\nSelect the correct media (number): ",
            min(len(tmdb_results), MAX_RESULTS_DISPLAY) - 1,
        )

        selected_media: Dict[str, Any] = tmdb_results[target_tmdb_index]
        refined_query: str = (
            f"{extract_title(selected_media)} {extract_year(selected_media)}"
        )

        raw_results: List[Dict[str, Any]] = search_torrents(client, refined_query)
        processed_results: List[Dict[str, Any]] = filter_and_sort_results(raw_results)

        resolution_groups: Dict[str, List[Dict[str, Any]]] = group_by_resolution(
            processed_results
        )

        if not resolution_groups:
            app_logger.warning(
                "No torrents found meeting criteria with standard resolutions."
            )
            return

        print("\nAvailable Resolutions:")
        available_resolutions: List[str] = list(resolution_groups.keys())
        for idx, res_key in enumerate(available_resolutions):
            print(f"[{idx}] {res_key} ({len(resolution_groups[res_key])} results)")

        target_res_index: int = select_from_list(
            "\nSelect desired resolution (number): ", len(available_resolutions) - 1
        )

        selected_resolution: str = available_resolutions[target_res_index]
        final_results: List[Dict[str, Any]] = resolution_groups[selected_resolution]

        print(f"\nTop Torrents for {selected_resolution}:")
        for idx, result in enumerate(final_results[:MAX_RESULTS_DISPLAY]):
            print(
                f"[{idx}] {result.get('fileName')} | Seeds: {result.get('nbSeeders')}"
            )

        target_torrent_index: int = select_from_list(
            "\nSelect a torrent to download (number): ",
            min(len(final_results), MAX_RESULTS_DISPLAY) - 1,
        )

        target_torrent: Dict[str, Any] = final_results[target_torrent_index]
        magnet_uri: str = target_torrent.get("fileUrl", "")

        # Convert to an absolute, platform-aware path
        base_path: Path = Path(config.base_media_dir).resolve()
        save_directory: Path = base_path / "unsorted"

        if config.dry_run:
            app_logger.info("[DRY RUN MODE ACTIVE]")
            app_logger.info(f"Target Directory: {save_directory}")
            app_logger.info(f"Target Magnet URI: {magnet_uri}")
            app_logger.info("Download bypassed.")
        else:
            try:
                client.torrents_add(urls=magnet_uri, save_path=str(save_directory))
                app_logger.info(f"Torrent added to queue. Target: {save_directory}")
            except Conflict409Error:
                app_logger.warning(
                    "Torrent already exists in the qBittorrent transfer list."
                )

    except KeyboardInterrupt:
        app_logger.info("Process interrupted by user. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
