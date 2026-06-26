"""Schemas for active torrent transfer state returned by the /transfers endpoint.

TransferInfo and TransferHashInfo come from medialab-contracts; the response
envelope below is this service's own.
"""

from medialab_contracts import TransferHashInfo, TransferInfo
from pydantic import BaseModel

__all__ = ["TransferHashInfo", "TransferInfo", "TransferInfoResponse"]


class TransferInfoResponse(BaseModel):
    """Envelope returned by the /transfers endpoint."""

    status: str
    message: str
    data: list[TransferInfo]
