"""Tests for AppConfig fields."""

from torrent_downloader.core.config import AppConfig


class TestMediaMountPath:
    def test_defaults_to_none(self) -> None:
        cfg = AppConfig(_env_file=None)
        assert cfg.media_mount_path is None

    def test_accepts_media_mount_path(self) -> None:
        cfg = AppConfig(_env_file=None, media_mount_path="/media")
        assert cfg.media_mount_path == "/media"


class TestVpnInterfaces:
    def test_defaults_to_the_gluetun_tunnel_interface(self) -> None:
        cfg = AppConfig(_env_file=None)
        assert cfg.vpn_interface_allowlist == ("tun0",)

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
