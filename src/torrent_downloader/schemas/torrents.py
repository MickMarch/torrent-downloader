"""Schemas for torrent search results returned by the qBittorrent plugin search."""

from pydantic import BaseModel


class TorrentResult(BaseModel):
    """A single torrent entry as returned by the qBittorrent search plugin."""

    fileName: str
    fileUrl: str
    nbSeeders: int
    nbLeechers: int
    siteUrl: str
    descrLink: str
    fileSize: int
    languages: list[str] = []
    """Audio languages parsed from the name (PTN names); empty when untagged."""
    multiAudio: bool = False
    """More than one audio track (``MULTi`` / ``DUAL``), usually incl. the original."""


class TorrentSearchResponse(BaseModel):
    """Envelope returned by the /search/torrents endpoint, keyed by resolution group."""

    status: str
    message: str
    data: dict[str, list[TorrentResult]]
