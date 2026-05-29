"""Tests for ErrorCode enum and AppException pure logic."""

import pytest

from torrent_downloader.core.errors import AppException, ErrorCode


class TestErrorCode:
    def test_has_qb_unavailable(self) -> None:
        assert ErrorCode.QB_UNAVAILABLE

    def test_has_vpn_not_bound(self) -> None:
        assert ErrorCode.VPN_NOT_BOUND

    def test_has_path_not_found(self) -> None:
        assert ErrorCode.PATH_NOT_FOUND

    def test_has_permission_denied(self) -> None:
        assert ErrorCode.PERMISSION_DENIED

    def test_has_invalid_input(self) -> None:
        assert ErrorCode.INVALID_INPUT

    def test_has_internal_error(self) -> None:
        assert ErrorCode.INTERNAL_ERROR

    def test_values_are_strings(self) -> None:
        for code in ErrorCode:
            assert isinstance(code.value, str)


class TestAppException:
    def test_stores_status_code(self) -> None:
        exc = AppException(status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found.")
        assert exc.status_code == 404

    def test_stores_code(self) -> None:
        exc = AppException(status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found.")
        assert exc.code == ErrorCode.PATH_NOT_FOUND

    def test_stores_detail(self) -> None:
        exc = AppException(status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found.")
        assert exc.detail == "Not found."

    def test_is_exception(self) -> None:
        exc = AppException(status_code=503, code=ErrorCode.QB_UNAVAILABLE, detail="Unavailable.")
        assert isinstance(exc, Exception)
