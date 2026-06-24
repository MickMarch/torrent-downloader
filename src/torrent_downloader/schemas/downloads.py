"""Schemas for the /download endpoint request and acknowledgement response."""

from typing import Literal

from pydantic import BaseModel

MediaType = Literal["movie", "show"]


class DownloadRequest(BaseModel):
    """Payload submitted to initiate a torrent download.

    Attributes:
        magnet_uri (str): Magnet link for the torrent to be added.
        media_type (MediaType): Determines which configured save path the server resolves.
        dry_run (bool): When True, validates the request without submitting it to the daemon.
    """

    magnet_uri: str
    media_type: MediaType
    dry_run: bool = False


class DownloadResponse(BaseModel):
    """Acknowledgement returned after a download submission attempt."""

    status: str
    message: str
