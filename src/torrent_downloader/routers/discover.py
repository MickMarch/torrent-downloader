"""Discover router: trending and popular-by-genre titles and genre lists from TMDB."""

from fastapi import APIRouter, Query, Request
from fastapi import status as fastapi_status
from medialab_contracts import DiscoverResponse, GenresResponse, MediaType

from torrent_downloader.core.constants import TAG_DISCOVER
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_SEARCH, limiter
from torrent_downloader.core.logger import app_logger
from torrent_downloader.schemas.errors import ErrorResponse
from torrent_downloader.services.tmdb import (
    TMDB_FIRST_PAGE,
    TMDB_MAX_PAGE,
    TmdbUnavailableError,
    get_discover,
    get_genres,
    get_recommendations,
)

router = APIRouter(prefix="/discover", tags=[TAG_DISCOVER])

RECOMMENDATIONS_MIN_LIMIT: int = 1

_DISCOVER_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Missing or invalid API key."},
    422: {"model": ErrorResponse, "description": "Invalid media type or query parameter."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    503: {"model": ErrorResponse, "description": "TMDB unconfigured or unavailable."},
}


def _tmdb_unavailable(error: TmdbUnavailableError) -> AppException:
    app_logger.warning(f"Discover request failed: {error}")
    return AppException(
        status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
        code=ErrorCode.TMDB_UNAVAILABLE,
        detail="TMDB is unavailable.",
    )


@router.get(
    "/{media_type}",
    response_model=DiscoverResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns trending titles, or the most popular in a genre or already released.",
    responses=_DISCOVER_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_discover(
    request: Request,
    media_type: MediaType,
    genre: int | None = None,
    page: int = Query(default=TMDB_FIRST_PAGE, ge=TMDB_FIRST_PAGE, le=TMDB_MAX_PAGE),
    released: bool = False,
) -> DiscoverResponse:
    """One TMDB page: trending this week without ``genre``, popular in ``genre``
    with it. ``released`` replaces trending with the most popular titles
    already out at home (digital or physical for movies, aired for shows)."""
    try:
        return get_discover(media_type, genre=genre, page=page, released=released)
    except TmdbUnavailableError as error:
        raise _tmdb_unavailable(error) from error


@router.get(
    "/{media_type}/recommendations/{tmdb_id}",
    response_model=DiscoverResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns TMDB's recommendations for a title.",
    responses=_DISCOVER_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_discover_recommendations(
    request: Request,
    media_type: MediaType,
    tmdb_id: int,
    released: bool = False,
    limit: int | None = Query(default=None, ge=RECOMMENDATIONS_MIN_LIMIT),
) -> DiscoverResponse:
    """TMDB's first page of recommendations, in its order; ``released`` keeps
    only titles out at home, ``limit`` caps the list."""
    try:
        return get_recommendations(media_type, tmdb_id, released=released, limit=limit)
    except TmdbUnavailableError as error:
        raise _tmdb_unavailable(error) from error


@router.get(
    "/{media_type}/genres",
    response_model=GenresResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns TMDB's genre list for the media type.",
    responses=_DISCOVER_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT_SEARCH)
def api_discover_genres(request: Request, media_type: MediaType) -> GenresResponse:
    """Genre ids and names, usable as ``genre`` on the discover route."""
    try:
        return get_genres(media_type)
    except TmdbUnavailableError as error:
        raise _tmdb_unavailable(error) from error
