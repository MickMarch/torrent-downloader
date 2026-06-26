"""Tests for ErrorCode enum and AppException pure logic."""

from medialab_contracts import CommonErrorCode

from torrent_downloader.core.errors import AppException, ErrorCode


class TestErrorCode:
    def test_has_service_specific_codes(self) -> None:
        # Shared codes are asserted via the superset test below; here we only
        # check this service's own codes exist.
        assert ErrorCode.QB_UNAVAILABLE
        assert ErrorCode.VPN_NOT_BOUND
        assert ErrorCode.TRANSFER_NOT_FOUND

    def test_is_superset_of_common_error_code(self) -> None:
        # Every shared code must be present with the same value, sourced from
        # CommonErrorCode so a rename in contracts surfaces here.
        for common in CommonErrorCode:
            assert ErrorCode[common.name].value == common.value


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
