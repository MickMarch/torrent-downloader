"""Tests for DownloadRequest schema: media_type + required tmdb_id."""

import pytest
from medialab_contracts import MediaType
from pydantic import ValidationError

from torrent_downloader.schemas.downloads import DownloadRequest

_MAGNET = "magnet:?xt=urn:btih:abc"
_TMDB_ID = 27205


class TestDownloadRequestMediaType:
    def test_wires_media_type_to_the_shared_enum(self) -> None:
        # MediaType's own value/validation behaviour is covered in
        # medialab-contracts; here we only assert DownloadRequest uses it.
        payload = DownloadRequest(magnet_uri=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.media_type is MediaType.MOVIE

    def test_requires_media_type(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(magnet_uri=_MAGNET, tmdb_id=_TMDB_ID)

    def test_has_no_save_path_field(self) -> None:
        payload = DownloadRequest(magnet_uri=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert not hasattr(payload, "save_path")

    def test_dry_run_defaults_false(self) -> None:
        payload = DownloadRequest(magnet_uri=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.dry_run is False


class TestDownloadRequestTmdbId:
    def test_accepts_tmdb_id(self) -> None:
        payload = DownloadRequest(magnet_uri=_MAGNET, media_type="movie", tmdb_id=_TMDB_ID)
        assert payload.tmdb_id == _TMDB_ID

    def test_tmdb_id_is_required(self) -> None:
        with pytest.raises(ValidationError):
            DownloadRequest(magnet_uri=_MAGNET, media_type="movie")
