"""Settings router: read and change the declared runtime tunables."""

from fastapi import APIRouter, Depends, Request
from fastapi import status as fastapi_status
from medialab_contracts import SettingsResponse, SettingUpdate, SettingView

from torrent_downloader.core.auth import verify_api_key
from torrent_downloader.core.constants import TAG_SYSTEM
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import RATE_LIMIT_DEFAULT, limiter
from torrent_downloader.core.settings import UnknownSettingError, runtime_settings
from torrent_downloader.schemas.errors import ErrorResponse

router = APIRouter(prefix="/settings", tags=[TAG_SYSTEM], dependencies=[Depends(verify_api_key)])

_STATUS_SUCCESS = "success"
_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Missing or invalid API key."},
    404: {"model": ErrorResponse, "description": "Unknown setting."},
    422: {"model": ErrorResponse, "description": "Value out of bounds or wrong type."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
}


def _unknown(key: str) -> AppException:
    return AppException(
        status_code=fastapi_status.HTTP_404_NOT_FOUND,
        code=ErrorCode.INVALID_INPUT,
        detail=f"Unknown setting: {key}",
    )


@router.get(
    "",
    response_model=SettingsResponse,
    summary="Every runtime setting with its effective value and source.",
    responses=_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def list_settings(request: Request) -> SettingsResponse:
    return SettingsResponse(status=_STATUS_SUCCESS, settings=runtime_settings.views())


@router.put(
    "/{key}",
    response_model=SettingView,
    summary="Override one setting; applies on the next use.",
    responses=_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def set_setting(request: Request, key: str, payload: SettingUpdate) -> SettingView:
    try:
        return runtime_settings.set(key, payload.value)
    except UnknownSettingError as error:
        raise _unknown(key) from error
    except ValueError as error:
        raise AppException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.INVALID_INPUT,
            detail=str(error),
        ) from error


@router.delete(
    "/{key}",
    response_model=SettingView,
    summary="Drop the override; the .env value (or default) applies again.",
    responses=_RESPONSES,
)
@limiter.limit(RATE_LIMIT_DEFAULT)
def reset_setting(request: Request, key: str) -> SettingView:
    try:
        return runtime_settings.reset(key)
    except UnknownSettingError as error:
        raise _unknown(key) from error
