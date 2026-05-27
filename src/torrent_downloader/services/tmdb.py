"""TMDB API client functions for multi-search queries and result normalisation."""

from typing import Any, Dict, List

import requests

from torrent_downloader.core.cache import app_cache
from torrent_downloader.core.config import config

TMDB_SEARCH_URL: str = "https://api.themoviedb.org/3/search/multi"
HTTP_STATUS_OK: int = 200
VALID_MEDIA_TYPES: set[str] = {"movie", "tv"}


@app_cache.memoize(expire=config.cache_expiration_seconds)
def search_tmdb_multi(query: str) -> List[Dict[str, Any]]:
    """Queries TMDB for matching media and caches the response."""
    if not config.tmdb_api_key:
        return []

    params: Dict[str, str] = {
        "api_key": config.tmdb_api_key,
        "query": query,
        "language": config.target_language,
    }

    response: requests.Response = requests.get(TMDB_SEARCH_URL, params=params)

    if response.status_code == HTTP_STATUS_OK:
        data: Dict[str, Any] = response.json()
        results: List[Dict[str, Any]] = data.get("results", [])
        return [item for item in results if item.get("media_type") in VALID_MEDIA_TYPES]

    return []


def extract_year(tmdb_item: Dict[str, Any]) -> str:
    """Extracts the initial release year from a TMDB payload."""
    date_str: str = tmdb_item.get("release_date", "") or tmdb_item.get(
        "first_air_date", ""
    )
    if date_str:
        return date_str.split("-")[0]
    return ""


def extract_title(tmdb_item: Dict[str, Any]) -> str:
    """Extracts the primary title from a TMDB payload."""
    return tmdb_item.get("title", "") or tmdb_item.get("name", "")


def extract_media_type(tmdb_item: Dict[str, Any]) -> str:
    """Extracts the media type from a TMDB payload."""
    return tmdb_item.get("media_type", "") or tmdb_item.get("name", "")
