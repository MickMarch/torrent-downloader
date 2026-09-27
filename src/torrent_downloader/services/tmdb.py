"""TMDB API client functions: multi-search, details, discover lists, normalisation."""

from datetime import UTC, datetime
from typing import Any

import requests
from medialab_contracts import (
    DiscoverItem,
    DiscoverResponse,
    Episode,
    GenresResponse,
    MediaType,
    Season,
    SeriesEpisodesResponse,
)

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


# Series episodes: every season and episode of a show, specials excluded.
# Cached like discover, since a season list changes only when TMDB adds an
# episode, days apart.

ENDPOINT_TV: str = "tv"
ENDPOINT_SEASON: str = "season"
ENDPOINT_EPISODES: str = "episodes"
PARAM_APPEND_TO_RESPONSE: str = "append_to_response"
APPEND_SEPARATOR: str = ","
# TMDB accepts at most this many appended sub-requests per call.
TMDB_APPEND_MAX_SEASONS: int = 20
SPECIALS_SEASON_NUMBER: int = 0

FIELD_SEASONS: str = "seasons"
FIELD_EPISODES: str = "episodes"
FIELD_STATUS: str = "status"
FIELD_NEXT_EPISODE: str = "next_episode_to_air"
FIELD_SEASON_NUMBER: str = "season_number"
FIELD_EPISODE_NUMBER: str = "episode_number"
FIELD_NAME: str = "name"
FIELD_AIR_DATE: str = "air_date"
FIELD_OVERVIEW: str = "overview"
FIELD_STILL_PATH: str = "still_path"
FIELD_RUNTIME: str = "runtime"
FIELD_EPISODE_COUNT: str = "episode_count"
FIELD_POSTER_PATH: str = "poster_path"


def _season_key(season_number: int) -> str:
    """The path suffix TMDB uses both in URLs and as the appended-response key."""
    return f"{ENDPOINT_SEASON}/{season_number}"


def _to_episode(raw: dict[str, Any]) -> Episode:
    return Episode(
        season=raw[FIELD_SEASON_NUMBER],
        episode=raw[FIELD_EPISODE_NUMBER],
        title=raw.get(FIELD_NAME) or "",
        air_date=raw.get(FIELD_AIR_DATE) or None,
        overview=raw.get(FIELD_OVERVIEW) or "",
        still_path=raw.get(FIELD_STILL_PATH),
        runtime_minutes=raw.get(FIELD_RUNTIME),
    )


def _to_season(raw: dict[str, Any]) -> Season:
    return Season(
        season=raw[FIELD_SEASON_NUMBER],
        name=raw.get(FIELD_NAME) or "",
        episode_count=raw.get(FIELD_EPISODE_COUNT) or 0,
        air_date=raw.get(FIELD_AIR_DATE) or None,
        poster_path=raw.get(FIELD_POSTER_PATH),
        overview=raw.get(FIELD_OVERVIEW) or "",
    )


def _fetch_series_with_seasons(
    series_id: int, season_numbers: list[int]
) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    """Refetches the series with every season appended, one round trip."""
    series_path: str = f"{ENDPOINT_TV}/{series_id}"
    appended: str = APPEND_SEPARATOR.join(_season_key(n) for n in season_numbers)
    data: dict[str, Any] = _tmdb_get(series_path, {PARAM_APPEND_TO_RESPONSE: appended})
    return data, {n: data.get(_season_key(n)) or {} for n in season_numbers}


def _fetch_seasons_individually(
    series_id: int, season_numbers: list[int]
) -> dict[int, dict[str, Any]]:
    series_path: str = f"{ENDPOINT_TV}/{series_id}"
    return {n: _tmdb_get(f"{series_path}/{_season_key(n)}", {}) for n in season_numbers}


def get_series_episodes(series_id: int) -> SeriesEpisodesResponse:
    """Every season and episode of a show in (season, episode) order, specials dropped."""
    key = (CACHE_NAMESPACE_DISCOVER, ENDPOINT_EPISODES, series_id, config.target_language)
    cached = app_cache.get(key)
    if cached is not None:
        return SeriesEpisodesResponse.model_validate(cached)

    series: dict[str, Any] = _tmdb_get(f"{ENDPOINT_TV}/{series_id}", {})
    season_summaries: list[dict[str, Any]] = sorted(
        (
            raw
            for raw in series.get(FIELD_SEASONS, [])
            if raw.get(FIELD_SEASON_NUMBER) != SPECIALS_SEASON_NUMBER
        ),
        key=lambda raw: raw[FIELD_SEASON_NUMBER],
    )
    season_numbers: list[int] = [raw[FIELD_SEASON_NUMBER] for raw in season_summaries]

    season_details: dict[int, dict[str, Any]]
    if not season_numbers:
        season_details = {}
    elif len(season_numbers) <= TMDB_APPEND_MAX_SEASONS:
        series, season_details = _fetch_series_with_seasons(series_id, season_numbers)
    else:
        season_details = _fetch_seasons_individually(series_id, season_numbers)

    episodes: list[Episode] = [
        _to_episode(raw)
        for n in season_numbers
        for raw in sorted(
            season_details[n].get(FIELD_EPISODES, []), key=lambda raw: raw[FIELD_EPISODE_NUMBER]
        )
    ]
    next_raw: dict[str, Any] | None = series.get(FIELD_NEXT_EPISODE)
    result = SeriesEpisodesResponse(
        tmdb_id=series_id,
        seasons=[_to_season(raw) for raw in season_summaries],
        episodes=episodes,
        next_episode=_to_episode(next_raw) if next_raw else None,
        status=series.get(FIELD_STATUS) or "",
    )
    app_cache.set(key, result.model_dump(mode="json"), expire=config.discover_cache_seconds)
    return result
