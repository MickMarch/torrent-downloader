"""TMDB API client functions: multi-search, details, discover lists, normalisation."""

from datetime import UTC, datetime
from typing import Any

import requests
from medialab_contracts import DiscoverItem, DiscoverResponse, GenresResponse, MediaType

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config

TMDB_BASE_URL: str = "https://api.themoviedb.org/3"
TMDB_SEARCH_URL: str = f"{TMDB_BASE_URL}/search/multi"
TMDB_MOVIE_URL: str = f"{TMDB_BASE_URL}/movie"
TMDB_TV_URL: str = f"{TMDB_BASE_URL}/tv"
HTTP_STATUS_OK: int = 200
VALID_MEDIA_TYPES: set[str] = {"movie", "tv"}


@app_cache.memoize(expire=config.cache_expiration_seconds)
def search_tmdb_multi(query: str) -> list[dict[str, Any]]:
    """Queries TMDB for matching media and caches the response."""
    if not config.tmdb_api_key:
        return []

    params: dict[str, str] = {
        "api_key": config.tmdb_api_key,
        "query": query,
        "language": config.target_language,
    }

    response: requests.Response = requests.get(TMDB_SEARCH_URL, params=params)

    if response.status_code == HTTP_STATUS_OK:
        data: dict[str, Any] = response.json()
        results: list[dict[str, Any]] = data.get("results", [])
        return [item for item in results if item.get("media_type") in VALID_MEDIA_TYPES]

    return []


def extract_year(tmdb_item: dict[str, Any]) -> str:
    """Extracts the initial release year from a TMDB payload."""
    date_str: str = tmdb_item.get("release_date", "") or tmdb_item.get("first_air_date", "")
    if date_str:
        return date_str.split("-")[0]
    return ""


def extract_title(tmdb_item: dict[str, Any]) -> str:
    """Extracts the primary title from a TMDB payload."""
    return tmdb_item.get("title", "") or tmdb_item.get("name", "")


def extract_media_type(tmdb_item: dict[str, Any]) -> str:
    """Extracts the media type from a TMDB payload."""
    return tmdb_item.get("media_type", "")


@app_cache.memoize(expire=config.cache_expiration_seconds)
def get_movie_details(movie_id: int) -> dict[str, Any]:
    """Fetches full movie details from TMDB by movie ID."""
    if not config.tmdb_api_key:
        return {}

    params: dict[str, str] = {
        "api_key": config.tmdb_api_key,
        "language": config.target_language,
    }

    response: requests.Response = requests.get(f"{TMDB_MOVIE_URL}/{movie_id}", params=params)

    if response.status_code == HTTP_STATUS_OK:
        return response.json()

    return {}


@app_cache.memoize(expire=config.cache_expiration_seconds)
def get_tv_details(series_id: int) -> dict[str, Any]:
    """Fetches full TV series details from TMDB by series ID."""
    if not config.tmdb_api_key:
        return {}

    params: dict[str, str] = {
        "api_key": config.tmdb_api_key,
        "language": config.target_language,
    }

    response: requests.Response = requests.get(f"{TMDB_TV_URL}/{series_id}", params=params)

    if response.status_code == HTTP_STATUS_OK:
        return response.json()

    return {}


# Discover: trending, popular-by-genre and genre lists. Cached with explicit
# get/set so ``discover_cache_seconds`` is read at write time, not at import.

DISCOVER_MIN_VOTES: int = 200
DISCOVER_SORT_BY: str = "popularity.desc"
TRENDING_WINDOW: str = "week"
# TMDB rejects page numbers above this, whatever total_pages reports.
TMDB_MAX_PAGE: int = 500
TMDB_FIRST_PAGE: int = 1
TMDB_REQUEST_TIMEOUT_SECONDS: int = 10
YEAR_LENGTH: int = 4

ENDPOINT_TRENDING: str = "trending"
ENDPOINT_DISCOVER: str = "discover"
ENDPOINT_GENRES: str = "genre"
CACHE_NAMESPACE_DISCOVER: str = "tmdb_discover"

TMDB_TYPE_BY_MEDIA_TYPE: dict[MediaType, str] = {
    MediaType.MOVIE: "movie",
    MediaType.SHOW: "tv",
}
TITLE_FIELD_BY_MEDIA_TYPE: dict[MediaType, str] = {
    MediaType.MOVIE: "title",
    MediaType.SHOW: "name",
}
DATE_FIELD_BY_MEDIA_TYPE: dict[MediaType, str] = {
    MediaType.MOVIE: "release_date",
    MediaType.SHOW: "first_air_date",
}


class TmdbUnavailableError(Exception):
    """TMDB is unconfigured, unreachable, or answered with an error."""


def _tmdb_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if not config.tmdb_api_key:
        raise TmdbUnavailableError("TMDB API key is not configured.")
    query: dict[str, Any] = {
        "api_key": config.tmdb_api_key,
        "language": config.target_language,
        **params,
    }
    try:
        response: requests.Response = requests.get(
            f"{TMDB_BASE_URL}/{path}", params=query, timeout=TMDB_REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as error:
        raise TmdbUnavailableError(f"TMDB request failed: {path}") from error
    if response.status_code != HTTP_STATUS_OK:
        raise TmdbUnavailableError(f"TMDB returned {response.status_code} for {path}")
    return response.json()


def _to_discover_item(raw: dict[str, Any], media_type: MediaType) -> DiscoverItem:
    date: str = raw.get(DATE_FIELD_BY_MEDIA_TYPE[media_type]) or ""
    return DiscoverItem(
        tmdb_id=raw["id"],
        media_type=media_type,
        title=raw.get(TITLE_FIELD_BY_MEDIA_TYPE[media_type]) or "",
        year=date[:YEAR_LENGTH] or None,
        overview=raw.get("overview") or "",
        vote_average=raw.get("vote_average") or 0.0,
        poster_path=raw.get("poster_path"),
    )


def get_discover(
    media_type: MediaType, genre: int | None = None, page: int = TMDB_FIRST_PAGE
) -> DiscoverResponse:
    """Trending titles this week, or the most popular in ``genre``, one TMDB page."""
    endpoint: str = ENDPOINT_TRENDING if genre is None else ENDPOINT_DISCOVER
    key = (
        CACHE_NAMESPACE_DISCOVER,
        endpoint,
        media_type.value,
        genre,
        page,
        config.target_language,
    )
    cached = app_cache.get(key)
    if cached is not None:
        return DiscoverResponse.model_validate(cached)

    tmdb_type: str = TMDB_TYPE_BY_MEDIA_TYPE[media_type]
    params: dict[str, Any] = {"page": page}
    if genre is None:
        path = f"{ENDPOINT_TRENDING}/{tmdb_type}/{TRENDING_WINDOW}"
    else:
        path = f"{ENDPOINT_DISCOVER}/{tmdb_type}"
        params |= {
            "with_genres": genre,
            "sort_by": DISCOVER_SORT_BY,
            "vote_count.gte": DISCOVER_MIN_VOTES,
        }
    data: dict[str, Any] = _tmdb_get(path, params)

    result = DiscoverResponse(
        items=[_to_discover_item(raw, media_type) for raw in data.get("results", [])],
        page=data.get("page", page),
        total_pages=min(data.get("total_pages", page), TMDB_MAX_PAGE),
        cached_at=datetime.now(UTC),
    )
    app_cache.set(key, result.model_dump(mode="json"), expire=config.discover_cache_seconds)
    return result


def get_genres(media_type: MediaType) -> GenresResponse:
    """TMDB's genre list for the media type, in ``target_language``."""
    key = (CACHE_NAMESPACE_DISCOVER, ENDPOINT_GENRES, media_type.value, config.target_language)
    cached = app_cache.get(key)
    if cached is not None:
        return GenresResponse.model_validate(cached)

    tmdb_type: str = TMDB_TYPE_BY_MEDIA_TYPE[media_type]
    data: dict[str, Any] = _tmdb_get(f"{ENDPOINT_GENRES}/{tmdb_type}/list", {})
    result = GenresResponse.model_validate({"genres": data.get("genres", [])})
    app_cache.set(key, result.model_dump(mode="json"), expire=config.discover_cache_seconds)
    return result
