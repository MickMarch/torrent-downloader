"""Tests for DownloadRequest schema: media_type replaces save_path."""

import pytest
from pydantic import ValidationError

from torrent_downloader.schemas.downloads import DownloadRequest


class TestDownloadRequestMediaType:
    def test_accepts_movie_media_type(self) -> None:
        payload = DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc", media_type="movie")
        assert payload.media_type == "movie"

    def test_accepts_show_media_type(self) -> None:
        payload = DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc", media_type="show")
        assert payload.media_type == "show"

    def test_rejects_invalid_media_type(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc", media_type="documentary")

    def test_requires_media_type(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc")

    def test_has_no_save_path_field(self) -> None:
        payload = DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc", media_type="movie")
        assert not hasattr(payload, "save_path")

    def test_dry_run_defaults_false(self) -> None:
        payload = DownloadRequest(magnet_uri="magnet:?xt=urn:btih:abc", media_type="movie")
        assert payload.dry_run is False
