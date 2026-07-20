"""Tests for DownloadRequest schema: source_url + media_type + required tmdb_id."""

import pytest
from medialab_contracts import MediaType
from pydantic import ValidationError

from torrent_downloader.schemas.downloads import DownloadRequest

_MAGNET = "magnet:?xt=urn:btih:abc"
_TORRENT_URL = "https://www.torlock.com/tor/1924049.torrent"
_TMDB_ID = 27205


class TestDownloadRequestSourceUrl:
    def test_accepts_a_magnet_source_url(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.source_url == _MAGNET

    def test_accepts_a_torrent_file_source_url(self) -> None:
        payload = DownloadRequest(source_url=_TORRENT_URL, media_type="show", tmdb_id=_TMDB_ID)
        assert payload.source_url == _TORRENT_URL

    def test_requires_source_url(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(media_type="movie", tmdb_id=_TMDB_ID)

    def test_has_no_magnet_uri_field(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert not hasattr(payload, "magnet_uri")


class TestDownloadRequestMediaType:
    def test_wires_media_type_to_the_shared_enum(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.media_type is MediaType.MOVIE

    def test_requires_media_type(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(source_url=_MAGNET, tmdb_id=_TMDB_ID)

    def test_has_no_save_path_field(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert not hasattr(payload, "save_path")

    def test_dry_run_defaults_false(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.dry_run is False


class TestDownloadRequestTmdbId:
    def test_accepts_tmdb_id(self) -> None:
        payload = DownloadRequest(source_url=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.tmdb_id == _TMDB_ID

    def test_tmdb_id_is_required(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(source_url=_MAGNET, media_type="movie")
