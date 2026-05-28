"""HTTP layer tests for system endpoints: /health, /cache, and /storage."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


class TestHealthRoute:
    def test_returns_200(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert client.get("/api/v1/health").status_code == 200

    def test_response_has_required_fields(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        body = client.get("/api/v1/health").json()
        assert "status" in body
        assert "uptime_seconds" in body
        assert "vpn_interface_bound" in body

    def test_status_is_online(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert client.get("/api/v1/health").json()["status"] == "online"

    def test_uptime_is_non_negative(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert client.get("/api/v1/health").json()["uptime_seconds"] >= 0

    def test_vpn_bound_false_when_client_unavailable(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert client.get("/api/v1/health").json()["vpn_interface_bound"] is False

    def test_vpn_bound_true_when_interface_matches(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=mocker.MagicMock())
        mocker.patch("torrent_downloader.routers.system.is_vpn_bound", return_value=True)
        assert client.get("/api/v1/health").json()["vpn_interface_bound"] is True

    def test_vpn_bound_false_when_interface_wrong(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=mocker.MagicMock())
        mocker.patch("torrent_downloader.routers.system.is_vpn_bound", return_value=False)
        assert client.get("/api/v1/health").json()["vpn_interface_bound"] is False


class TestCacheClearRoute:
    def test_returns_200(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.app_cache")
        assert client.delete("/api/v1/cache").status_code == 200

    def test_response_cleared_is_true(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.app_cache")
        assert client.delete("/api/v1/cache").json()["cleared"] is True

    def test_cache_clear_is_called(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_cache = mocker.patch("torrent_downloader.routers.system.app_cache")
        client.delete("/api/v1/cache")
        mock_cache.clear.assert_called_once()


class TestStorageRoute:
    def _mock_disk_usage(self, mocker: MockerFixture, total_gb: float = 500.0, used_gb: float = 200.0) -> None:
        free_gb = total_gb - used_gb
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "used_percent": round((used_gb / total_gb) * 100, 2),
            },
        )

    def test_returns_200(self, client: TestClient, mocker: MockerFixture) -> None:
        self._mock_disk_usage(mocker)
        assert client.get("/api/v1/storage?path=/some/path").status_code == 200

    def test_response_has_required_fields(self, client: TestClient, mocker: MockerFixture) -> None:
        self._mock_disk_usage(mocker)
        body = client.get("/api/v1/storage?path=/some/path").json()
        assert "path" in body
        assert "total_gb" in body
        assert "used_gb" in body
        assert "free_gb" in body
        assert "used_percent" in body

    def test_response_echoes_path(self, client: TestClient, mocker: MockerFixture) -> None:
        self._mock_disk_usage(mocker)
        body = client.get("/api/v1/storage?path=/some/path").json()
        assert body["path"] == "/some/path"

    def test_returns_400_on_invalid_path(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=FileNotFoundError("No such file or directory"),
        )
        assert client.get("/api/v1/storage?path=/invalid/path").status_code == 400

    def test_returns_400_on_permission_error(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=PermissionError("Permission denied"),
        )
        assert client.get("/api/v1/storage?path=/restricted/path").status_code == 400

    def test_missing_path_param_returns_422(self, client: TestClient) -> None:
        assert client.get("/api/v1/storage").status_code == 422
