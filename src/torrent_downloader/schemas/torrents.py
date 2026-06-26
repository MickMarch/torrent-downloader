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


class TorrentSearchResponse(BaseModel):
    """Envelope returned by the /search/torrents endpoint, keyed by resolution group."""

    status: str
    message: str
    data: dict[str, list[TorrentResult]]
