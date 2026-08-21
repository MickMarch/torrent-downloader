"""Tests for AppConfig fields."""

from torrent_downloader.core.config import AppConfig


class TestMediaHostPath:
    def test_defaults_to_none(self) -> None:
        cfg = AppConfig(_env_file=None)
        assert cfg.media_host_path is None

    def test_accepts_media_host_path(self) -> None:
        cfg = AppConfig(_env_file=None, media_host_path="F:\\Media")
        assert cfg.media_host_path == "F:\\Media"


class TestVpnInterfaces:
    def test_defaults_to_nordlynx(self) -> None:
        cfg = AppConfig(_env_file=None)
        assert cfg.vpn_interface_allowlist == ("NordLynx",)

    def test_parses_comma_separated(self) -> None:
        cfg = AppConfig(_env_file=None, vpn_interfaces="NordLynx,NordLayer-NordLynx")
        assert cfg.vpn_interface_allowlist == ("NordLynx", "NordLayer-NordLynx")

    def test_strips_surrounding_whitespace(self) -> None:
        cfg = AppConfig(_env_file=None, vpn_interfaces=" NordLynx , NordLayer-NordLynx ")
        assert cfg.vpn_interface_allowlist == ("NordLynx", "NordLayer-NordLynx")

    def test_drops_empty_entries(self) -> None:
        cfg = AppConfig(_env_file=None, vpn_interfaces="NordLynx,,")
        assert cfg.vpn_interface_allowlist == ("NordLynx",)

    def test_empty_string_yields_empty_allowlist(self) -> None:
        cfg = AppConfig(_env_file=None, vpn_interfaces="")
        assert cfg.vpn_interface_allowlist == ()
