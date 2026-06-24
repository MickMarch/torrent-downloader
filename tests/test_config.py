"""Tests for AppConfig v1.1 media-type path fields."""

import pytest
from pydantic import ValidationError

from torrent_downloader.core.config import AppConfig


class TestMediaTypePathFields:
    def test_requires_movies_path(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(
                _env_file=None,
                tv_path="/media/tv",
                movies_host_path="F:\\Media\\Movies",
                tv_host_path="F:\\Media\\TV",
            )

    def test_requires_tv_path(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(
                _env_file=None,
                movies_path="/media/movies",
                movies_host_path="F:\\Media\\Movies",
                tv_host_path="F:\\Media\\TV",
            )

    def test_requires_movies_host_path(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(
                _env_file=None,
                movies_path="/media/movies",
                tv_path="/media/tv",
                tv_host_path="F:\\Media\\TV",
            )

    def test_requires_tv_host_path(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(
                _env_file=None,
                movies_path="/media/movies",
                tv_path="/media/tv",
                movies_host_path="F:\\Media\\Movies",
            )

    def test_accepts_all_four_fields(self) -> None:
        cfg = AppConfig(
            _env_file=None,
            movies_path="/media/movies",
            tv_path="/media/tv",
            movies_host_path="F:\\Media\\Movies",
            tv_host_path="F:\\Media\\TV",
        )
        assert cfg.movies_path == "/media/movies"
        assert cfg.tv_path == "/media/tv"
        assert cfg.movies_host_path == "F:\\Media\\Movies"
        assert cfg.tv_host_path == "F:\\Media\\TV"
