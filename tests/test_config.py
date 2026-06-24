"""Tests for AppConfig v1.1 media_host_path field."""

import pytest
from pydantic import ValidationError

from torrent_downloader.core.config import AppConfig


class TestMediaHostPath:
    def test_requires_media_host_path(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(_env_file=None)

    def test_accepts_media_host_path(self) -> None:
        cfg = AppConfig(_env_file=None, media_host_path="F:\\Media")
        assert cfg.media_host_path == "F:\\Media"
