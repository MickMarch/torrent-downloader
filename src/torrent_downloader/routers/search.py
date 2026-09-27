"""Search router: TMDB metadata lookup and qBittorrent plugin torrent search."""

from typing import Any

import qbittorrentapi
from fastapi import APIRouter, Request
from fastapi import status as fastapi_status
from medialab_contracts import MediaType, TorrentSearchScope
from pydantic import ValidationError

from torrent_downloader.core.config import config
from torrent_downloader.core.constants import TAG_SEARCH
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_SEARCH, limiter
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.errors import ErrorResponse
from torrent_downloader.schemas.tmdb import (
    TmdbMediaDetailResponse,
    TmdbSearchResponse,
    TmdbSearchResult,
)
from torrent_downloader.schemas.torrents import TorrentResult, TorrentSearchResponse
from torrent_downloader.services.language import annotate_and_filter
from torrent_downloader.services.qbittorrent import (
    SEARCH_CATEGORY_BY_MEDIA_TYPE,
    build_search_patterns,
    filter_and_sort_results,
    filter_by_scope,
    filter_by_year,
    get_torrent_client,
    group_by_resolution,
    run_pattern_searches,
    search_torrents,
    split_trailing_year,
    union_by_url,
)
from torrent_downloader.services.tmdb import (
    extract_media_type,
    extract_title,
    extract_year,
    get_movie_details,
    get_tv_details,
    search_tmdb_multi,
)

router = APIRouter(prefix="/search", tags=[TAG_SEARCH])


_SEARCH_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Missing or invalid API key."},
    422: {"model": ErrorResponse, "description": "Missing or invalid query parameter."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
}


@router.get(
    "/tmdb",
    response_model=TmdbSearchResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns formatted TMDB metadata for dispatcher selection.",
    responses=_SEARCH_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_search_tmdb(request: Request, query: str) -> TmdbSearchResponse:
    """Query TMDB for movies and TV shows matching the search string."""
    raw_results: list[dict[str, Any]] = search_tmdb_multi(query)
    formatted_results: list[TmdbSearchResult] = [
        TmdbSearchResult(
            tmdb_id=item["id"],
            title=extract_title(item),
            year=extract_year(item),
            media_type=extract_media_type(item),
            overview=item.get("overview", ""),
            vote_average=item.get("vote_average", 0.0),
            poster_path=item.get("poster_path"),
        )
        for item in raw_results
    ]
    return TmdbSearchResponse(status="success", message="", data=formatted_results)


@router.get(
    "/torrents",
    response_model=TorrentSearchResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns torrents grouped by resolution.",
    responses={
        **_SEARCH_ERROR_RESPONSES,
        503: {"model": ErrorResponse, "description": "qBittorrent client unavailable."},
    },
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_search_torrents(
    request: Request,
    query: str,
    media_type: MediaType,
    season: int | None = None,
    episode: int | None = None,
    alt_query: str | None = None,
) -> TorrentSearchResponse:
    """Search for torrents via qBittorrent plugins and return results grouped by resolution.

    ``media_type`` is required. For shows, an optional ``season`` (and ``episode``)
    targets the search at a specific season/episode instead of the show as a whole.
    ``alt_query`` is a second spelling of the same title (what the user typed,
    when TMDB's canonical title differs from release names); its results are
    unioned with the primary query's.
    """
    try:
        scope: TorrentSearchScope = TorrentSearchScope(
            media_type=media_type, season=season, episode=episode
        )
    except ValidationError as error:
        raise AppException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.INVALID_INPUT,
            detail="Invalid season/episode combination for the requested media type.",
        ) from error

    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise AppException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.QB_UNAVAILABLE,
            detail="qBittorrent client unavailable.",
        )

    queries: list[str] = [query]
    if alt_query and alt_query.strip().casefold() != query.strip().casefold():
        queries.append(alt_query.strip())
    _prefetch_patterns(client, queries, scope)
    batches: list[list[dict[str, Any]]] = []
    for q in queries:
        batches.append(_search_pipeline(client, q, scope))
        if scope.media_type is MediaType.MOVIE:
            batches.append(_movie_bare_title_pass(client, q, scope))
    scoped_results: list[dict[str, Any]] = union_by_url(batches)
    grouped: dict[str, list[TorrentResult]] = {
        resolution: [TorrentResult(**item) for item in items]
        for resolution, items in group_by_resolution(scoped_results).items()
    }

    return TorrentSearchResponse(status="success", message="", data=grouped)


def _prefetch_patterns(
    client: qbittorrentapi.Client, queries: list[str], scope: TorrentSearchScope
) -> None:
    """Runs every pattern the pipeline will ask for in one concurrent batch, so
    the sequential passes below all hit the cache."""
    patterns: list[str] = []
    for q in queries:
        patterns.extend(build_search_patterns(q, scope))
        if scope.media_type is MediaType.MOVIE and (split := split_trailing_year(q)):
            patterns.extend(build_search_patterns(split[0], scope))
    run_pattern_searches(client, patterns, SEARCH_CATEGORY_BY_MEDIA_TYPE[scope.media_type])


def _search_pipeline(
    client: qbittorrentapi.Client, query: str, scope: TorrentSearchScope
) -> list[dict[str, Any]]:
    raw_results: list[dict[str, Any]] = search_torrents(client, query, scope)
    processed_results: list[dict[str, Any]] = filter_and_sort_results(raw_results)
    language_results: list[dict[str, Any]] = annotate_and_filter(
        processed_results,
        target_code=config.target_language,
        policy=config.audio_language_filter,
    )
    return filter_by_scope(language_results, scope)


def _movie_bare_title_pass(
    client: qbittorrentapi.Client, query: str, scope: TorrentSearchScope
) -> list[dict[str, Any]]:
    """Some plugins answer only the bare title, others only "Title YYYY", so a
    movie always searches both; bare-title hits count only when PTN dates
    them to the requested year."""
    split = split_trailing_year(query)
    if split is None:
        return []
    title, year = split
    app_logger.info(f"Also searching '{title}' filtered to year {year}.")
    return filter_by_year(_search_pipeline(client, title, scope), year)


@router.get(
    "/tmdb/movie/{movie_id}",
    response_model=TmdbMediaDetailResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns full TMDB details for a movie by ID.",
    responses=_SEARCH_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_get_movie_details(request: Request, movie_id: int) -> TmdbMediaDetailResponse:
    """Fetch detailed movie metadata from TMDB by movie ID."""
    raw: dict[str, Any] = get_movie_details(movie_id)
    if not raw:
        return TmdbMediaDetailResponse(status="error", message="Movie not found.", data=None)
    return TmdbMediaDetailResponse(status="success", message="", data=raw)


@router.get(
    "/tmdb/show/{series_id}",
    response_model=TmdbMediaDetailResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns full TMDB details for a TV series by ID.",
    responses=_SEARCH_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_get_tv_details(request: Request, series_id: int) -> TmdbMediaDetailResponse:
    """Fetch detailed TV series metadata from TMDB by series ID."""
    raw: dict[str, Any] = get_tv_details(series_id)
    if not raw:
        return TmdbMediaDetailResponse(status="error", message="TV series not found.", data=None)
    return TmdbMediaDetailResponse(status="success", message="", data=raw)
