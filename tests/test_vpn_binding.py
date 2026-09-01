"""Tests for VPN interface allowlist matching and the qBittorrent binding check.

The binding check is a hard, non-bypassable invariant: it must fail closed on an
empty allowlist, an unreadable interface, or any exception.
"""

import pytest

from torrent_downloader.services.qbittorrent import is_vpn_bound, matches_vpn_allowlist

NORDLYNX = "NordLynx"
NORDLAYER = "NordLayer-NordLynx"
BOTH_INTERFACES = (NORDLYNX, NORDLAYER)
INTERFACE_KEY = "current_interface_name"


@pytest.fixture
def qb_client(mocker):
    """A qBittorrent client stub whose reported interface is settable per test."""

    def _make(interface: str | None):
        client = mocker.MagicMock()
        preferences = {} if interface is None else {INTERFACE_KEY: interface}
        client.app_preferences.return_value = preferences
        return client

    return _make


class TestMatchesVpnAllowlist:
    def test_exact_match(self) -> None:
        assert matches_vpn_allowlist(NORDLYNX, (NORDLYNX,)) is True

    def test_match_is_case_insensitive(self) -> None:
        assert matches_vpn_allowlist("nordlynx", ("NORDLYNX",)) is True

    def test_match_tolerates_surrounding_whitespace(self) -> None:
        assert matches_vpn_allowlist("  NordLynx  ", (" NordLynx ",)) is True

    def test_second_interface_matches(self) -> None:
        assert matches_vpn_allowlist(NORDLAYER, BOTH_INTERFACES) is True

    def test_substring_does_not_match(self) -> None:
        """Guards against anyone relaxing the compare into a prefix match."""
        assert matches_vpn_allowlist("NordLynx2", (NORDLYNX,)) is False

    def test_unlisted_interface_does_not_match(self) -> None:
        assert matches_vpn_allowlist("Ethernet", BOTH_INTERFACES) is False

    def test_empty_allowlist_denies_everything(self) -> None:
        """The core invariant: no configured interfaces means no downloads."""
        assert matches_vpn_allowlist(NORDLYNX, ()) is False

    def test_empty_interface_name_denies(self) -> None:
        assert matches_vpn_allowlist("", (NORDLYNX,)) is False

    def test_whitespace_interface_name_denies(self) -> None:
        assert matches_vpn_allowlist("   ", (NORDLYNX,)) is False


class TestIsVpnBound:
    def test_accepts_interface_in_explicit_allowlist(self, qb_client) -> None:
        assert is_vpn_bound(qb_client(NORDLYNX), (NORDLYNX,)) is True

    def test_accepts_second_interface(self, qb_client) -> None:
        assert is_vpn_bound(qb_client(NORDLAYER), BOTH_INTERFACES) is True

    def test_rejects_interface_outside_allowlist(self, qb_client) -> None:
        assert is_vpn_bound(qb_client("Ethernet"), BOTH_INTERFACES) is False

    def test_empty_allowlist_argument_denies(self, qb_client, mocker) -> None:
        """An explicit empty list must deny, never silently fall back to config."""
        mocker.patch(
            "torrent_downloader.services.qbittorrent.config",
            vpn_interface_allowlist=BOTH_INTERFACES,
        )
        assert is_vpn_bound(qb_client(NORDLYNX), ()) is False

    def test_falls_back_to_config_when_argument_omitted(self, qb_client, mocker) -> None:
        mocker.patch(
            "torrent_downloader.services.qbittorrent.config",
            vpn_interface_allowlist=(NORDLAYER,),
        )
        assert is_vpn_bound(qb_client(NORDLAYER)) is True
        assert is_vpn_bound(qb_client(NORDLYNX)) is False

    def test_returns_false_when_preferences_raise(self, qb_client, mocker) -> None:
        client = qb_client(NORDLYNX)
        client.app_preferences.side_effect = RuntimeError("connection lost")
        assert is_vpn_bound(client, (NORDLYNX,)) is False

    def test_returns_false_when_interface_key_missing(self, qb_client) -> None:
        assert is_vpn_bound(qb_client(None), (NORDLYNX,)) is False

    def test_logs_bound_interface_on_match(self, qb_client, mocker) -> None:
        logger = mocker.patch("torrent_downloader.services.qbittorrent.app_logger")
        is_vpn_bound(qb_client(NORDLAYER), BOTH_INTERFACES)
        logged = logger.info.call_args[0][0]
        assert NORDLAYER in logged

    def test_logs_critical_on_mismatch(self, qb_client, mocker) -> None:
        logger = mocker.patch("torrent_downloader.services.qbittorrent.app_logger")
        is_vpn_bound(qb_client("Ethernet"), BOTH_INTERFACES)
        logged = logger.critical.call_args[0][0]
        assert "Ethernet" in logged
        assert NORDLYNX in logged
