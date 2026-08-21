"""qBittorrent Web API client: connection, transfer management, and plugin-based search."""

import time
from collections.abc import Sequence
from typing import Any

import PTN
import qbittorrentapi
from medialab_contracts import MediaType, TorrentSearchScope
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

VPN_INTERFACE_PREFERENCE_KEY: str = "current_interface_name"
NO_INTERFACES_CONFIGURED: str = "<none configured>"

SEARCH_COMPLETION_STATUS: str = "Stopped"
POLL_INTERVAL_SECONDS: float = 1.0
EMPTY_SEEDER_COUNT: int = 0
DEFAULT_SEARCH_ID: int = 0
RES_4K_KEYS: set[str] = {"4k", "2160p"}
RES_1080_KEYS: set[str] = {"1080p"}
RES_720_KEYS: set[str] = {"720p"}

RES_GROUP_4K: str = "4K"
RES_GROUP_1080: str = "1080p"
RES_GROUP_720: str = "720p"
# Catch-all for releases with no parseable or unrecognised resolution (common
# for older/SD TV, e.g. HDTV/DVDRip rips) so they are never silently dropped.
RES_GROUP_OTHER: str = "Other"

MAGNET_URL_PREFIX: str = "magnet:?"
TORRENT_FILE_SUFFIX: str = ".torrent"
HTTP_URL_PREFIX: str = "http"

SEARCH_CATEGORY_MOVIES: str = "movies"
SEARCH_CATEGORY_TV: str = "tv"
SEARCH_CATEGORY_BY_MEDIA_TYPE: dict[MediaType, str] = {
    MediaType.MOVIE: SEARCH_CATEGORY_MOVIES,
    MediaType.SHOW: SEARCH_CATEGORY_TV,
}

# Season packs are usually released as "Show Season 2" while single episodes
# use the S02E05 tag, so the two scopes take different pattern shapes.
SEASON_TAG_TEMPLATE: str = "Season {season}"
EPISODE_TAG_TEMPLATE: str = "S{season:02d}E{episode:02d}"


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


def matches_vpn_allowlist(current_interface: str, allowlist: Sequence[str]) -> bool:
    """
    Case-insensitive membership test for a bound interface against the allowlist.

    An empty allowlist matches nothing: an unconfigured allowlist must never be
    read as "allow any interface".
    """
    if not allowlist:
        return False

    normalized: str = current_interface.strip().lower()
    if not normalized:
        return False

    return normalized in {name.strip().lower() for name in allowlist}


def is_vpn_bound(
    client: qbittorrentapi.Client,
    accepted_interfaces: Sequence[str] | None = None,
) -> bool:
    """
    Verifies that qBittorrent is bound to one of the accepted VPN interfaces.
    This guarantees traffic halts if the VPN drops, bypassing the need for host OS process checks.

    Falls back to the configured allowlist when accepted_interfaces is omitted.
    Passing an empty sequence denies every interface rather than falling back.
    """
    allowlist: tuple[str, ...] = (
        tuple(accepted_interfaces)
        if accepted_interfaces is not None
        else config.vpn_interface_allowlist
    )

    try:
        preferences: dict[str, Any] = client.app_preferences()
        current_interface: str = str(preferences.get(VPN_INTERFACE_PREFERENCE_KEY, ""))

        if matches_vpn_allowlist(current_interface, allowlist):
            app_logger.info(
                f"VPN check passed. qBittorrent is bound to '{current_interface}' "
                f"(accepted: {', '.join(allowlist)})."
            )
            return True

        app_logger.critical(
            f"SECURITY ALERT: qBittorrent is bound to '{current_interface}', but requires "
            f"one of: {', '.join(allowlist) or NO_INTERFACES_CONFIGURED}. Download rejected."
        )
        return False
    except Exception as e:
        app_logger.error(f"Failed to verify network interface binding: {e}")
        return False


def build_search_pattern(query: str, scope: TorrentSearchScope) -> str:
    """Refines the search query with a season/episode tag from the scope.

    Whole-title and whole-series scopes search on the bare query. A season scope
    appends ``Season N`` (how season packs are usually named); an episode scope
    appends ``S0NE0M`` so trackers return the targeted episode rather than the
    highest-seeded (usually latest) season.
    """
    if scope.season is None:
        return query
    if scope.episode is None:
        return f"{query} {SEASON_TAG_TEMPLATE.format(season=scope.season)}"
    return f"{query} {EPISODE_TAG_TEMPLATE.format(season=scope.season, episode=scope.episode)}"


def _parsed_seasons(parsed_season: Any) -> list[int]:
    """Normalises PTN's season field (int, list, or None) to a list of ints."""
    if parsed_season is None:
        return []
    if isinstance(parsed_season, list):
        return [int(s) for s in parsed_season]
    return [int(parsed_season)]


def filter_by_scope(
    results: list[dict[str, Any]], scope: TorrentSearchScope
) -> list[dict[str, Any]]:
    """Drops results that do not match the requested season/episode.

    Movie and whole-series scopes are returned unchanged. For a season or episode
    scope, each result's filename is PTN-parsed and classified:

    - primary: the release targets exactly the requested season (a single-season
      pack, or the exact requested episode within it).
    - fallback: a multi-season range pack that spans the requested season, or a
      complete-series pack (no parseable season). Kept so the set is never empty.

    Primary matches are returned before fallbacks; everything else is dropped.
    """
    if scope.season is None:
        return results

    primary: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []

    for result in results:
        parsed: dict[str, Any] = PTN.parse(result.get("fileName", ""))
        seasons: list[int] = _parsed_seasons(parsed.get("season"))
        episode: Any = parsed.get("episode")

        if not seasons:
            fallback.append(result)
            continue

        if len(seasons) > 1:
            if scope.season in seasons:
                fallback.append(result)
            continue

        if seasons[0] != scope.season:
            continue

        if scope.episode is None or episode == scope.episode:
            primary.append(result)
        elif episode is None:
            fallback.append(result)

    return primary + fallback


def execute_plugin_search(
    client: qbittorrentapi.Client, query: str, category: str
) -> list[dict[str, Any]]:
    """Runs the qBittorrent plugin search loop and returns raw results.

    Polls until all plugins report completion or the configured timeout is reached,
    at which point any still-running plugins are forcibly stopped before results
    are fetched.
    """
    search_job: dict[str, Any] = client.search_start(
        pattern=query, plugins="all", category=category
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


def _scope_cache_key(query: str, scope: TorrentSearchScope) -> str:
    """Builds a cache key that varies by query and requested season/episode.

    Without the season/episode in the key a season-2 search would return a cached
    season-5 result set for the same show title.
    """
    return f"torrent_search_{query}_{scope.media_type.value}_{scope.season}_{scope.episode}"


def search_torrents(
    client: qbittorrentapi.Client, query: str, scope: TorrentSearchScope
) -> list[dict[str, Any]]:
    """Returns cached torrent results or executes a new scope-aware search."""
    cache_key: str = _scope_cache_key(query, scope)
    cached_results: Any = app_cache.get(cache_key)

    if cached_results is not None:
        app_logger.info(f"Returning cached results for query: '{query}' scope: {cache_key}")
        return cached_results

    pattern: str = build_search_pattern(query, scope)
    category: str = SEARCH_CATEGORY_BY_MEDIA_TYPE[scope.media_type]
    app_logger.info(f"Initiating new search for pattern: '{pattern}' category: '{category}'")
    parsed_results: list[dict[str, Any]] = execute_plugin_search(client, pattern, category)

    app_logger.info(f"Search completed. Found {len(parsed_results)} total results.")
    app_cache.set(cache_key, parsed_results, expire=config.cache_expiration_seconds)
    return parsed_results


def is_addable_source(file_url: str) -> bool:
    """True if the URL is a usable torrent source.

    A magnet URI or an http ``.torrent`` file URL add to qBittorrent directly;
    an http HTML details page has its magnet scraped at download time. All three
    are torrent sources the plugins return, so any magnet or http URL qualifies.
    """
    return file_url.startswith(MAGNET_URL_PREFIX) or file_url.startswith(HTTP_URL_PREFIX)


def filter_and_sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filters by minimum seeders, keeps addable sources, sorts by seeders descending."""
    filtered: list[dict[str, Any]] = []

    for res in results:
        file_url: str = res.get("fileUrl", "")
        seed_count: int = res.get("nbSeeders", EMPTY_SEEDER_COUNT)

        has_enough_seeds: bool = seed_count >= config.minimum_seeders

        if has_enough_seeds and is_addable_source(file_url):
            filtered.append(res)

    filtered.sort(key=lambda x: x.get("nbSeeders", EMPTY_SEEDER_COUNT), reverse=True)
    return filtered


def group_by_resolution(
    results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Categorizes parsed torrent dictionaries by target resolutions.

    Results with no parseable or unrecognised resolution fall into an ``Other``
    bucket rather than being dropped, so valid low-tag releases still reach the
    caller.
    """
    grouped: dict[str, list[dict[str, Any]]] = {
        RES_GROUP_4K: [],
        RES_GROUP_1080: [],
        RES_GROUP_720: [],
        RES_GROUP_OTHER: [],
    }

    for result in results:
        parsed: dict[str, Any] = PTN.parse(result.get("fileName", ""))
        resolution: str = str(parsed.get("resolution", "")).lower()

        if resolution in RES_4K_KEYS:
            grouped[RES_GROUP_4K].append(result)
        elif resolution in RES_1080_KEYS:
            grouped[RES_GROUP_1080].append(result)
        elif resolution in RES_720_KEYS:
            grouped[RES_GROUP_720].append(result)
        else:
            grouped[RES_GROUP_OTHER].append(result)

    return {k: v for k, v in grouped.items() if v}
