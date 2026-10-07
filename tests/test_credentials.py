"""Credential health: tracker, classification on live calls, the probe loop, the setting."""

import asyncio

import pytest
import requests
from medialab_contracts import (
    CREDENTIAL_QB_API_KEY,
    CREDENTIAL_TMDB_API_KEY,
    CredentialStatus,
)
from qbittorrentapi.exceptions import APIConnectionError, Forbidden403Error

from torrent_downloader.core import settings as settings_module
from torrent_downloader.core.credentials import CredentialTracker, credentials
from torrent_downloader.services import credential_probe, qbittorrent, tmdb

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401


@pytest.fixture(autouse=True)
def fresh_tracker():
    credentials.reset()
    yield
    credentials.reset()


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.ok = status_code == HTTP_OK

    def json(self) -> dict:
        return {}


class TestTracker:
    def test_starts_unknown_for_owned_credentials(self) -> None:
        tracker = CredentialTracker()
        snapshot = tracker.snapshot()
        assert set(snapshot) == {CREDENTIAL_TMDB_API_KEY, CREDENTIAL_QB_API_KEY}
        assert all(s.status is CredentialStatus.UNKNOWN for s in snapshot.values())

    def test_marks_record_time_and_detail(self) -> None:
        tracker = CredentialTracker()
        tracker.mark_invalid(CREDENTIAL_TMDB_API_KEY, "HTTP 401")
        state = tracker.snapshot()[CREDENTIAL_TMDB_API_KEY]
        assert state.status is CredentialStatus.INVALID
        assert state.detail == "HTTP 401"
        assert state.checked_at is not None
        tracker.mark_ok(CREDENTIAL_TMDB_API_KEY)
        assert tracker.snapshot()[CREDENTIAL_TMDB_API_KEY].status is CredentialStatus.OK


class TestTmdbClassification:
    def test_unauthorized_marks_invalid(self, mocker) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", "k")
        mocker.patch.object(requests, "get", return_value=_Response(HTTP_UNAUTHORIZED))
        tmdb._get_or_unavailable(tmdb.TMDB_CONFIGURATION_URL, {})
        state = credentials.snapshot()[CREDENTIAL_TMDB_API_KEY]
        assert state.status is CredentialStatus.INVALID
        assert str(HTTP_UNAUTHORIZED) in state.detail

    def test_success_marks_ok(self, mocker) -> None:
        mocker.patch.object(requests, "get", return_value=_Response(HTTP_OK))
        tmdb._get_or_unavailable(tmdb.TMDB_CONFIGURATION_URL, {})
        assert credentials.snapshot()[CREDENTIAL_TMDB_API_KEY].status is CredentialStatus.OK

    def test_transport_failure_marks_unreachable(self, mocker) -> None:
        mocker.patch.object(requests, "get", side_effect=requests.ConnectionError("down"))
        with pytest.raises(tmdb.TmdbUnavailableError):
            tmdb._get_or_unavailable(tmdb.TMDB_CONFIGURATION_URL, {})
        assert (
            credentials.snapshot()[CREDENTIAL_TMDB_API_KEY].status is CredentialStatus.UNREACHABLE
        )

    def test_probe_uses_the_configuration_endpoint_with_the_key(self, mocker) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", "k")
        get = mocker.patch.object(requests, "get", return_value=_Response(HTTP_OK))
        tmdb.probe_tmdb()
        url = get.call_args.args[0]
        assert url == tmdb.TMDB_CONFIGURATION_URL
        assert get.call_args.kwargs["params"]["api_key"] == "k"

    def test_probe_without_a_key_marks_invalid_without_a_call(self, mocker) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", None)
        get = mocker.patch.object(requests, "get")
        tmdb.probe_tmdb()
        get.assert_not_called()
        assert credentials.snapshot()[CREDENTIAL_TMDB_API_KEY].status is CredentialStatus.INVALID


class TestQbittorrentClassification:
    def test_forbidden_marks_invalid_and_returns_none(self, mocker) -> None:
        fake = mocker.Mock()
        fake.app_web_api_version.side_effect = Forbidden403Error("nope")
        mocker.patch.object(qbittorrent.qbittorrentapi, "Client", return_value=fake)
        assert qbittorrent.get_torrent_client() is None
        assert credentials.snapshot()[CREDENTIAL_QB_API_KEY].status is CredentialStatus.INVALID

    def test_connection_error_marks_unreachable(self, mocker) -> None:
        fake = mocker.Mock()
        fake.app_web_api_version.side_effect = APIConnectionError("down")
        mocker.patch.object(qbittorrent.qbittorrentapi, "Client", return_value=fake)
        assert qbittorrent.get_torrent_client() is None
        assert credentials.snapshot()[CREDENTIAL_QB_API_KEY].status is CredentialStatus.UNREACHABLE

    def test_success_marks_ok(self, mocker) -> None:
        fake = mocker.Mock()
        fake.app_web_api_version.return_value = "2.11"
        mocker.patch.object(qbittorrent.qbittorrentapi, "Client", return_value=fake)
        assert qbittorrent.get_torrent_client() is fake
        assert credentials.snapshot()[CREDENTIAL_QB_API_KEY].status is CredentialStatus.OK


class TestProbeLoop:
    def test_probes_after_startup_delay_then_on_the_interval(self, mocker) -> None:
        probe = mocker.patch.object(credential_probe, "probe_all")
        mocker.patch.object(credential_probe.config, "credential_check_interval_seconds", 42)
        waits: list[float] = []
        stop = asyncio.Event()

        async def fake_sleep(seconds: float) -> None:
            waits.append(seconds)
            if len(waits) >= 3:
                stop.set()

        asyncio.run(credential_probe.run_probe_loop(stop, sleep=fake_sleep, startup_delay=5.0))
        assert waits == [5.0, 42.0, 42.0]
        assert probe.call_count == 2

    def test_a_failing_probe_does_not_end_the_loop(self, mocker) -> None:
        probe = mocker.patch.object(credential_probe, "probe_all", side_effect=RuntimeError("x"))
        stop = asyncio.Event()
        calls = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal calls
            calls += 1
            if calls >= 3:
                stop.set()

        asyncio.run(credential_probe.run_probe_loop(stop, sleep=fake_sleep, startup_delay=0))
        assert probe.call_count == 2


class TestSetting:
    def test_interval_is_a_bounded_runtime_setting(self) -> None:
        spec = next(
            s for s in settings_module.SETTINGS if s.key == "credential_check_interval_seconds"
        )
        assert spec.min == settings_module.CREDENTIAL_CHECK_INTERVAL_MIN
        assert spec.max == settings_module.CREDENTIAL_CHECK_INTERVAL_MAX
        assert spec.min < spec.max
