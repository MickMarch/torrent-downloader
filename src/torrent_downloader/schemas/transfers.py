"""Schemas for active torrent transfer state returned by the /transfers endpoint."""

from pydantic import BaseModel


class TransferInfo(BaseModel):
    """Runtime state snapshot for a single qBittorrent torrent."""

    name: str
    size: int
    progress: float
    hash: str
    state: str
    download_speed: int
    upload_speed: int
    eta_seconds: int
    save_path: str


class TransferInfoResponse(BaseModel):
    """Envelope returned by the /transfers endpoint."""

    status: str
    message: str
    data: list[TransferInfo]


class TransferHashInfo(BaseModel):
    """Cached media-type metadata for a single torrent, keyed by hash."""

    media_type: str
    host_path: str
    save_path: str
