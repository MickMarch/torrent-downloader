"""HTTP layer tests for system endpoints: /health and /cache."""

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
