"""Search router: TMDB metadata lookup and qBittorrent plugin torrent search."""

from typing import Any

import qbittorrentapi
from fastapi import APIRouter, Request
from fastapi import status as fastapi_status

from torrent_downloader.core.constants import TAG_SEARCH
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_SEARCH, limiter
from torrent_downloader.schemas.errors import ErrorResponse
from torrent_downloader.schemas.tmdb import (
    TmdbMediaDetailResponse,
    TmdbSearchResponse,
    TmdbSearchResult,
)
from torrent_downloader.schemas.torrents import TorrentResult, TorrentSearchResponse
from torrent_downloader.services.qbittorrent import (
    filter_and_sort_results,
    get_torrent_client,
    group_by_resolution,
    search_torrents,
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
def api_search_torrents(request: Request, query: str) -> TorrentSearchResponse:
    """Search for torrents via qBittorrent plugins and return results grouped by resolution."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise AppException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.QB_UNAVAILABLE,
            detail="qBittorrent client unavailable.",
        )

    raw_results: list[dict[str, Any]] = search_torrents(client, query)
    processed_results: list[dict[str, Any]] = filter_and_sort_results(raw_results)
    grouped: dict[str, list[TorrentResult]] = {
        resolution: [TorrentResult(**item) for item in items]
        for resolution, items in group_by_resolution(processed_results).items()
    }

    return TorrentSearchResponse(status="success", message="", data=grouped)


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
    "/tmdb/tv/{series_id}",
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
