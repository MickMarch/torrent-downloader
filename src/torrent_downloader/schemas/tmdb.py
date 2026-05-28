"""Schemas for TMDB search results returned to the client."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TmdbSearchResult(BaseModel):
    """Normalised metadata for a single TMDB search result."""

    tmdb_id: int
    title: str
    year: str
    media_type: str
    overview: str
    vote_average: float
    poster_path: Optional[str]


class TmdbSearchResponse(BaseModel):
    """Envelope returned by the /search/tmdb endpoint."""

    status: str
    message: str
    data: List[TmdbSearchResult]


class TmdbMediaDetailResponse(BaseModel):
    """Envelope returned by the /search/tmdb/movie and /search/tmdb/tv endpoints."""

    status: str
    message: str
    data: Optional[Dict[str, Any]]
