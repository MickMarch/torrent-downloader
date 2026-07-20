"""Schemas for the /download endpoint request and acknowledgement response."""

from medialab_contracts import MediaType
from pydantic import BaseModel


class DownloadRequest(BaseModel):
    """Payload submitted to initiate a torrent download.

    Attributes:
        source_url (str): The torrent source - either a magnet URI or an http
            ``.torrent`` file URL. qBittorrent adds either directly; for a
            ``.torrent`` URL the info-hash is read back after the add.
        media_type (MediaType): Determines which configured save path the server resolves.
        tmdb_id (int): TMDB id of the selected title, cached for the orchestrator
            to resolve canonical metadata at completion time.
        dry_run (bool): When True, validates the request without submitting it to the daemon.
    """

    source_url: str
    media_type: MediaType
    tmdb_id: int
    dry_run: bool = False


class DownloadResponse(BaseModel):
    """Acknowledgement returned after a download submission attempt.

    ``torrent_hash`` is the resolved BTIH info-hash (parsed from a magnet, or
    read back from qBittorrent after adding a ``.torrent`` URL). It is ``None``
    when the hash could not be determined; the completion webhook backfills it.
    """

    status: str
    message: str
    torrent_hash: str | None = None
