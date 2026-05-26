"""Schemas for TMDB search results returned to the client."""

from typing import Any, Dict, List

from pydantic import BaseModel


class TmdbMovieInfo(BaseModel):
    """Normalised metadata for a single TMDB movie or TV show result."""

    title: str
    year: str
    media_type: str
    original_data: Dict[str, Any]


class TmdbMovieInfoResponse(BaseModel):
    """Envelope returned by the /search/tmdb endpoint."""

    status: str
    message: str
    data: List[TmdbMovieInfo]
