"""Schemas for the /download endpoint request and acknowledgement response."""

from medialab_contracts import MediaType
from pydantic import BaseModel


class DownloadRequest(BaseModel):
    """Payload submitted to initiate a torrent download.

    Attributes:
        magnet_uri (str): Magnet link for the torrent to be added.
        media_type (MediaType): Determines which configured save path the server resolves.
        tmdb_id (int): TMDB id of the selected title, cached for the orchestrator
            to resolve canonical metadata at completion time.
        dry_run (bool): When True, validates the request without submitting it to the daemon.
    """

    magnet_uri: str
    media_type: MediaType
    tmdb_id: int
    dry_run: bool = False


class DownloadResponse(BaseModel):
    """Acknowledgement returned after a download submission attempt."""

    status: str
    message: str
