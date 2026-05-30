"""API key authentication dependency for protected endpoints."""

from fastapi import Security
from fastapi.security import APIKeyHeader

from torrent_downloader.core.config import config
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.logger import app_logger

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    if api_key is None:
        app_logger.warning("Request rejected: missing X-API-Key header")
        raise AppException(status_code=403, code=ErrorCode.UNAUTHORIZED, detail="Missing API key.")
    if api_key != config.api_key:
        app_logger.warning("Request rejected: invalid API key")
        raise AppException(status_code=403, code=ErrorCode.UNAUTHORIZED, detail="Invalid API key.")
