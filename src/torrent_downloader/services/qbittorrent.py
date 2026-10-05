"""qBittorrent Web API client: connection, transfer management, and plugin-based search."""

import re
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from typing import Any

import PTN
import qbittorrentapi
from medialab_contracts import MediaType, TorrentSearchProgress, TorrentSearchScope
from qbittorrentapi.exceptions import APIConnectionError

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.torrents import TorrentResult
from torrent_downloader.schemas.transfers import TransferInfo
from torrent_downloader.services.search_progress import search_progress

search_timeout_override: ContextVar[int | None] = ContextVar(
    "search_timeout_override", default=None
)
"""A per-request search timeout, set by a route for the span of one search.
When set, patterns are run fresh rather than served from the cache, since a
caller asking for a longer wait wants more than the short run found."""

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
# qBittorrent's search status carries the running result count under this key.
SEARCH_STATUS_TOTAL_KEY: str = "total"
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
# Buckets an automatic pick may draw from, highest first. A pick falls
# through to the next lower bucket when the requested one is empty and never
# reaches ``Other``.
PICK_RESOLUTION_ORDER: tuple[str, ...] = (RES_GROUP_4K, RES_GROUP_1080, RES_GROUP_720)

MAGNET_URL_PREFIX: str = "magnet:?"
TORRENT_FILE_SUFFIX: str = ".torrent"
HTTP_URL_PREFIX: str = "http"

SEARCH_CATEGORY_MOVIES: str = "movies"
SEARCH_CATEGORY_TV: str = "tv"
SEARCH_CATEGORY_BY_MEDIA_TYPE: dict[MediaType, str] = {
    MediaType.MOVIE: SEARCH_CATEGORY_MOVIES,
    MediaType.SHOW: SEARCH_CATEGORY_TV,
}

# Releases carry the scene tag (S02, S02E05); "Season 2" in a pattern misses
# most of them. A scoped search runs the tagged pattern and the bare title,
# unions the two, and lets filter_by_scope pick.
SEASON_TAG_TEMPLATE: str = "S{season:02d}"
SEASON_WORD_TEMPLATE: str = "Season {season}"
EPISODE_TAG_TEMPLATE: str = "S{season:02d}E{episode:02d}"
# A movie query is "Title YYYY"; when that yields nothing the title alone is
# searched and results are kept only when their parsed year matches.
_TRAILING_YEAR = re.compile(r"^(?P<title>.+?)\s+(?P<year>(19|20)\d{2})$")
_RESULT_URL_KEY = "fileUrl"


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
            content_path=torrent.get("content_path", ""),
        )
        parsed_transfers.append(transfer_state)

    return parsed_transfers


def stop_seeding_transfers(client: qbittorrentapi.Client) -> None:
    """Stops torrent transfers from seeding in the client."""
    torrents: Any = client.torrents_info(status_filter=STATUS_FILTER_SEEDING)

    for torrent in torrents:
        client.torrents_pause(torrent.get("hash", ""))
        app_logger.info(f"Succesfully stopped torrent:{torrent.get('name', '')}")


def has_transfer(client: qbittorrentapi.Client, torrent_hash: str) -> bool:
    """Whether qBittorrent currently holds a torrent with this info-hash."""
    torrents: Any = client.torrents_info(torrent_hashes=torrent_hash.lower())
    return any(t.get("hash", "").lower() == torrent_hash.lower() for t in torrents)


def resume_transfer(client: qbittorrentapi.Client, torrent_hash: str) -> None:
    """Resume one torrent. A no-op on a torrent that is already running."""
    client.torrents_resume(torrent_hashes=torrent_hash.lower())
    app_logger.info(f"Resumed torrent {torrent_hash.lower()}")


def remove_transfer(
    client: qbittorrentapi.Client, torrent_hash: str, *, delete_files: bool = False
) -> None:
    """Remove one torrent from qBittorrent; its files only when asked."""
    client.torrents_delete(torrent_hashes=torrent_hash.lower(), delete_files=delete_files)
    app_logger.info(
        f"Removed torrent {torrent_hash.lower()} (files {'deleted' if delete_files else 'kept'})"
    )


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


def build_search_patterns(query: str, scope: TorrentSearchScope) -> list[str]:
    """The plugin patterns a scope needs, most specific first.

    Whole-title and whole-series scopes search the bare query. A season scope
    searches ``Title S0N``, ``Title Season N`` (uploaders use either) and the
    bare title (complete-series packs only surface there); an episode scope
    searches ``Title S0NE0M`` and ``Title S0N`` so a season pack remains a
    fallback.
    """
    if scope.season is None:
        return [query]
    season_tag = f"{query} {SEASON_TAG_TEMPLATE.format(season=scope.season)}"
    season_word = f"{query} {SEASON_WORD_TEMPLATE.format(season=scope.season)}"
    if scope.episode is None:
        return [season_tag, season_word, query]
    episode_tag = (
        f"{query} {EPISODE_TAG_TEMPLATE.format(season=scope.season, episode=scope.episode)}"
    )
    return [episode_tag, season_tag]


def build_search_pattern(query: str, scope: TorrentSearchScope) -> str:
    """The primary (most specific) pattern for a scope."""
    return build_search_patterns(query, scope)[0]


def split_trailing_year(query: str) -> tuple[str, int] | None:
    """``"Storks 2016"`` -> ``("Storks", 2016)``; ``None`` when no year trails."""
    match = _TRAILING_YEAR.match(query.strip())
    if match is None:
        return None
    return match.group("title"), int(match.group("year"))


def filter_by_year(results: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    """Keeps releases whose parsed year is ``year``. Releases with no parseable
    year are dropped: without the year in the pattern they are the noise."""
    kept: list[dict[str, Any]] = []
    for result in results:
        parsed_year = PTN.parse(result.get("fileName", "")).get("year")
        if parsed_year == year:
            kept.append(result)
    return kept


def union_by_url(batches: Sequence[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for batch in batches:
        for result in batch:
            url = result.get(_RESULT_URL_KEY, "")
            if url in seen:
                continue
            seen.add(url)
            merged.append(result)
    return merged


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
    client: qbittorrentapi.Client,
    query: str,
    category: str,
    timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Runs the qBittorrent plugin search loop and returns raw results.

    Polls until all plugins report completion or the timeout is reached (the
    configured one unless ``timeout_seconds`` is given), at which point any
    still-running plugins are forcibly stopped before results are fetched.
    """
    timeout: int = config.search_timeout_seconds if timeout_seconds is None else timeout_seconds
    search_progress.start(query, category)
    try:
        return _run_plugin_search(client, query, category, timeout)
    finally:
        search_progress.finish(query, category)


def _run_plugin_search(
    client: qbittorrentapi.Client, query: str, category: str, timeout: int
) -> list[dict[str, Any]]:
    search_job: dict[str, Any] = client.search_start(
        pattern=query, plugins="all", category=category
    )

    search_id: int = search_job.get("id", DEFAULT_SEARCH_ID)
    start_time: float = time.time()

    while True:
        elapsed: float = time.time() - start_time
        if elapsed >= timeout:
            app_logger.info(f"Search timeout reached ({timeout}s). Terminating hanging plugins.")
            client.search_stop(search_id=search_id)
            break

        status: list[dict[str, Any]] = client.search_status(search_id=search_id)
        if status:
            search_progress.update(
                query, category, results=int(status[0].get(SEARCH_STATUS_TOTAL_KEY, 0))
            )
            if status[0].get("status") == SEARCH_COMPLETION_STATUS:
                break

        time.sleep(POLL_INTERVAL_SECONDS)

    results: Any = client.search_results(search_id=search_id, limit=0)
    found: list[dict[str, Any]] = results.get("results", [])
    search_progress.update(query, category, results=len(found))
    return found


def _pattern_cache_key(pattern: str, category: str) -> str:
    """Raw plugin results are cached per pattern and category, so every query
    that shares a pattern (a season scope and its bare title, a TMDB title and
    a typed one) reuses one plugin run."""
    return f"torrent_search_{category}_{pattern.casefold()}"


def run_pattern_searches(
    client: qbittorrentapi.Client, patterns: Sequence[str], category: str
) -> dict[str, list[dict[str, Any]]]:
    """Raw results per pattern. Cached patterns are served from the cache; the
    rest run concurrently, so wall time is one search timeout, not one per
    pattern. qBittorrent runs several search jobs at once."""
    results: dict[str, list[dict[str, Any]]] = {}
    pending: list[str] = []
    # Read once here, in the request thread; the pool threads do not see the context.
    timeout_override: int | None = search_timeout_override.get()
    for pattern in dict.fromkeys(patterns):
        cached: Any = (
            None
            if timeout_override is not None
            else app_cache.get(_pattern_cache_key(pattern, category))
        )
        if cached is not None:
            app_logger.info(f"Returning cached results for pattern: '{pattern}'")
            results[pattern] = cached
        else:
            pending.append(pattern)
    if not pending:
        return results

    def run(pattern: str) -> list[dict[str, Any]]:
        app_logger.info(f"Initiating new search for pattern: '{pattern}' category: '{category}'")
        found = execute_plugin_search(client, pattern, category, timeout_override)
        app_logger.info(f"Search for '{pattern}' found {len(found)} results.")
        app_cache.set(
            _pattern_cache_key(pattern, category), found, expire=config.cache_expiration_seconds
        )
        return found

    workers = max(1, min(config.search_concurrency, len(pending)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pattern, found in zip(pending, pool.map(run, pending), strict=True):
            results[pattern] = found
    return results


def search_queries(query: str, alt_query: str | None) -> list[str]:
    """The primary query and, when it differs, the alternate spelling."""
    queries: list[str] = [query]
    if alt_query and alt_query.strip().casefold() != query.strip().casefold():
        queries.append(alt_query.strip())
    return queries


def request_patterns(queries: Sequence[str], scope: TorrentSearchScope) -> list[str]:
    """Every plugin pattern one search request runs: each query's scope
    patterns and, for a movie with a trailing year, the bare title's too.
    The prefetch runs exactly these; the progress endpoint reports on them."""
    patterns: list[str] = []
    for q in queries:
        patterns.extend(build_search_patterns(q, scope))
        if scope.media_type is MediaType.MOVIE and (split := split_trailing_year(q)):
            patterns.extend(build_search_patterns(split[0], scope))
    return list(dict.fromkeys(patterns))


def search_progress_for(
    query: str, alt_query: str | None, scope: TorrentSearchScope
) -> TorrentSearchProgress:
    """Where the search for these parameters stands, from the registry and
    the pattern cache; never touches qBittorrent."""
    category: str = SEARCH_CATEGORY_BY_MEDIA_TYPE[scope.media_type]
    patterns = request_patterns(search_queries(query, alt_query), scope)
    return search_progress.aggregate(
        patterns,
        category,
        timeout_seconds=config.search_timeout_seconds,
        cached_results=lambda p: app_cache.get(_pattern_cache_key(p, category)),
    )


def search_torrents(
    client: qbittorrentapi.Client, query: str, scope: TorrentSearchScope
) -> list[dict[str, Any]]:
    """Union of the raw results for every pattern the scope needs."""
    category: str = SEARCH_CATEGORY_BY_MEDIA_TYPE[scope.media_type]
    patterns = build_search_patterns(query, scope)
    by_pattern = run_pattern_searches(client, patterns, category)
    parsed_results: list[dict[str, Any]] = union_by_url([by_pattern[p] for p in patterns])
    app_logger.info(f"Search for '{query}' completed. {len(parsed_results)} total results.")
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


def is_exact_season_pack(name: str, season: int) -> bool:
    """Whether a release name targets exactly one whole season: a single parsed
    season equal to ``season`` and no episode. Single episodes, multi-episode
    releases, multi-season ranges and complete series packs all fail."""
    parsed: dict[str, Any] = PTN.parse(name)
    return _parsed_seasons(parsed.get("season")) == [season] and parsed.get("episode") is None


def is_exact_episode(name: str, season: int, episode: int) -> bool:
    """Whether a release name targets exactly one episode: a single parsed
    season equal to ``season`` and a single parsed episode equal to ``episode``.
    Season packs, multi-season ranges, multi-episode releases and complete
    series packs all fail this test."""
    parsed: dict[str, Any] = PTN.parse(name)
    return _parsed_seasons(parsed.get("season")) == [season] and parsed.get("episode") == episode


def pick_best(
    grouped: dict[str, list[TorrentResult]],
    *,
    season: int,
    episode: int | None,
    resolution: str,
    min_seeders: int,
) -> TorrentResult | None:
    """The automatic pick rule over grouped show search results.

    Pure: no I/O and ``grouped`` is not modified. In order: only releases
    naming exactly this episode (or, with ``episode`` unset, exactly this
    season's pack), only those with at least ``min_seeders``,
    the ``resolution`` bucket or failing that each lower bucket in
    ``PICK_RESOLUTION_ORDER`` (never ``Other``), then the most seeded release,
    ties broken by the larger file. ``None`` when nothing qualifies.
    """

    def targets(name: str) -> bool:
        if episode is None:
            return is_exact_season_pack(name, season)
        return is_exact_episode(name, season, episode)

    start: int = PICK_RESOLUTION_ORDER.index(resolution)
    for bucket in PICK_RESOLUTION_ORDER[start:]:
        candidates: list[TorrentResult] = [
            result
            for result in grouped.get(bucket, [])
            if result.nbSeeders >= min_seeders and targets(result.fileName)
        ]
        if candidates:
            return max(candidates, key=lambda result: (result.nbSeeders, result.fileSize))
    return None
