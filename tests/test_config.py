"""Tests for AppConfig v1.1 media_host_path field."""

from torrent_downloader.core.config import AppConfig


class TestMediaHostPath:
    def test_defaults_to_none(self) -> None:
        cfg = AppConfig(_env_file=None)
        assert cfg.media_host_path is None

    def test_accepts_media_host_path(self) -> None:
        cfg = AppConfig(_env_file=None, media_host_path="F:\\Media")
        assert cfg.media_host_path == "F:\\Media"
