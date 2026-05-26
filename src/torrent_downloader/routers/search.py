"""Search router: TMDB metadata lookup and qBittorrent plugin torrent search."""

from typing import Any, Dict, List

import qbittorrentapi
from fastapi import APIRouter, HTTPException
from fastapi import status as fastapi_status

from torrent_downloader.core.constants import TAG_SEARCH
from torrent_downloader.schemas.tmdb import TmdbMovieInfo, TmdbMovieInfoResponse
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
    search_tmdb_multi,
)

router = APIRouter(prefix="/search", tags=[TAG_SEARCH])


@router.get(
    "/tmdb",
    response_model=TmdbMovieInfoResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns formatted TMDB metadata for dispatcher selection.",
)
def api_search_tmdb(query: str) -> TmdbMovieInfoResponse:
    """Query TMDB for movies and TV shows matching the search string."""
    raw_results: List[Dict[str, Any]] = search_tmdb_multi(query)
    formatted_results: List[TmdbMovieInfo] = [
        TmdbMovieInfo(
            title=extract_title(item),
            year=extract_year(item),
            media_type=extract_media_type(item),
            original_data=item,
        )
        for item in raw_results
    ]
    return TmdbMovieInfoResponse(status="success", message="", data=formatted_results)


@router.get(
    "/torrents",
    response_model=TorrentSearchResponse,
    status_code=fastapi_status.HTTP_200_OK,
    summary="Returns torrents grouped by resolution.",
)
def api_search_torrents(query: str) -> TorrentSearchResponse:
    """Search for torrents via qBittorrent plugins and return results grouped by resolution."""
    client: qbittorrentapi.Client | None = get_torrent_client()
    if not client:
        raise HTTPException(status_code=503, detail="qBittorrent client unavailable.")

    raw_results: List[Dict[str, Any]] = search_torrents(client, query)
    processed_results: List[Dict[str, Any]] = filter_and_sort_results(raw_results)
    grouped: Dict[str, List[TorrentResult]] = {
        resolution: [TorrentResult(**item) for item in items]
        for resolution, items in group_by_resolution(processed_results).items()
    }

    return TorrentSearchResponse(status="success", message="", data=grouped)
