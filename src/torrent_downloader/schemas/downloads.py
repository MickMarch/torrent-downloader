"""Schemas for the /download endpoint request and acknowledgement response."""

from pydantic import BaseModel


class DownloadRequest(BaseModel):
    """Payload submitted to initiate a torrent download.

    Attributes:
        magnet_uri (str): Magnet link for the torrent to be added.
        save_path (str): Absolute path on the qBittorrent host where files will be saved.
        dry_run (bool): When True, validates the request without submitting it to the daemon.
    """

    magnet_uri: str
    save_path: str
    dry_run: bool = False


class DownloadResponse(BaseModel):
    """Acknowledgement returned after a download submission attempt."""

    status: str
    message: str
