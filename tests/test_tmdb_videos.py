"""Service tests for the TMDB trailer and teaser listing."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import diskcache
import pytest
import requests
from medialab_contracts import MediaType, VideosResponse, VideoType
from pytest_mock import MockerFixture

from torrent_downloader.services import tmdb
from torrent_downloader.services.tmdb import TmdbUnavailableError, get_videos

MOVIE_ID = 438631
SERIES_ID = 100088
SEASON = 2
HTTP_OK = 200
HTTP_SERVER_ERROR = 500
CACHE_TTL = 86400
OTHER_CACHE_TTL = 7200


def _video(key: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": f"id-{key}",
        "key": key,
        "name": f"Video {key}",
        "site": "YouTube",
        "type": "Trailer",
        "official": True,
        "published_at": "2024-03-01T12:00:00.000Z",
        "iso_639_1": "en",
        "iso_3166_1": "US",
        "size": 1080,
        **overrides,
    }


VIDEOS_PAYLOAD: dict[str, Any] = {
    "id": MOVIE_ID,
    "results": [
        _video("clip", type="Clip"),
        _video("featurette", type="Featurette"),
        _video("vimeo", site="Vimeo"),
        _video("teaser-unofficial", type="Teaser", official=False),
        _video("trailer-old", published_at="2023-01-01T00:00:00.000Z"),
        _video("trailer-undated", published_at=None),
        _video("trailer-unofficial", official=False, published_at="2024-06-01T00:00:00.000Z"),
        _video("teaser-official", type="Teaser", published_at="2024-05-01T00:00:00.000Z"),
        _video("trailer-new", published_at="2024-03-01T12:00:00.000Z", iso_639_1="fr"),
    ],
}

EXPECTED_ORDER = [
    "trailer-new",
    "trailer-old",
    "trailer-undated",
    "teaser-official",
    "trailer-unofficial",
    "teaser-unofficial",
]


def _response(payload: dict[str, Any], status_code: int = HTTP_OK) -> MagicMock:
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


@pytest.fixture
def cache(tmp_path: Path, mocker: MockerFixture) -> Iterator[diskcache.Cache]:
    temp_cache = diskcache.Cache(str(tmp_path / "cache"))
    mocker.patch.object(tmdb, "app_cache", temp_cache)
    yield temp_cache
    temp_cache.close()


@pytest.fixture(autouse=True)
def tmdb_config(mocker: MockerFixture) -> None:
    mocker.patch.object(tmdb.config, "tmdb_api_key", "tmdb-test-key")
    mocker.patch.object(tmdb.config, "target_language", "en")
    mocker.patch.object(tmdb.config, "discover_cache_seconds", CACHE_TTL)


def _mock_get(
    mocker: MockerFixture, payload: dict[str, Any], status_code: int = HTTP_OK
) -> MagicMock:
    return mocker.patch.object(tmdb.requests, "get", return_value=_response(payload, status_code))


def _url_and_params(mock_get: MagicMock) -> tuple[str, dict[str, Any]]:
    call = mock_get.call_args
    return call.args[0], call.kwargs["params"]


class TestRequests:
    def test_movie_path(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.MOVIE, MOVIE_ID)
        url, _ = _url_and_params(mock_get)
        assert url == f"{tmdb.TMDB_BASE_URL}/movie/{MOVIE_ID}/videos"

    def test_show_path(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.SHOW, SERIES_ID)
        url, _ = _url_and_params(mock_get)
        assert url == f"{tmdb.TMDB_BASE_URL}/tv/{SERIES_ID}/videos"

    def test_season_path_when_season_given(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.SHOW, SERIES_ID, season=SEASON)
        url, _ = _url_and_params(mock_get)
        assert url == f"{tmdb.TMDB_BASE_URL}/tv/{SERIES_ID}/season/{SEASON}/videos"

    def test_season_on_movie_is_rejected_before_any_request(
        self, cache, mocker: MockerFixture
    ) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        with pytest.raises(ValueError):
            get_videos(MediaType.MOVIE, MOVIE_ID, season=SEASON)
        mock_get.assert_not_called()

    def test_language_params_with_english_target(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.MOVIE, MOVIE_ID)
        _, params = _url_and_params(mock_get)
        assert params["api_key"] == "tmdb-test-key"
        assert params["language"] == "en"
        assert params["include_video_language"] == "en,null"

    def test_language_params_with_other_target_keep_english_fallback(
        self, cache, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(tmdb.config, "target_language", "fr")
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.MOVIE, MOVIE_ID)
        _, params = _url_and_params(mock_get)
        assert params["language"] == "fr"
        assert params["include_video_language"] == "fr,en,null"


class TestFilteringAndSorting:
    def test_returns_contract_model(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        assert isinstance(get_videos(MediaType.MOVIE, MOVIE_ID), VideosResponse)

    def test_keeps_only_youtube_trailers_and_teasers(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        keys = {v.key for v in get_videos(MediaType.MOVIE, MOVIE_ID).videos}
        assert "clip" not in keys
        assert "featurette" not in keys
        assert "vimeo" not in keys
        assert keys == set(EXPECTED_ORDER)

    def test_official_then_trailer_before_teaser_then_newest_first(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        assert [v.key for v in get_videos(MediaType.MOVIE, MOVIE_ID).videos] == EXPECTED_ORDER

    def test_video_fields_mapped(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        first = get_videos(MediaType.MOVIE, MOVIE_ID).videos[0]
        assert first.key == "trailer-new"
        assert first.name == "Video trailer-new"
        assert first.type is VideoType.TRAILER
        assert first.official is True
        assert first.published_at == datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
        assert first.language == "fr"

    def test_teaser_type_mapped(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        by_key = {v.key: v for v in get_videos(MediaType.MOVIE, MOVIE_ID).videos}
        assert by_key["teaser-official"].type is VideoType.TEASER

    def test_missing_or_blank_published_at_is_none(self, cache, mocker: MockerFixture) -> None:
        payload = {"results": [_video("blank", published_at=""), _video("absent")]}
        del payload["results"][1]["published_at"]
        _mock_get(mocker, payload)
        assert all(v.published_at is None for v in get_videos(MediaType.MOVIE, MOVIE_ID).videos)

    def test_no_results_is_empty_list(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {"id": MOVIE_ID, "results": []})
        assert get_videos(MediaType.MOVIE, MOVIE_ID).videos == []


class TestCaching:
    def test_second_call_does_not_hit_tmdb(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        first = get_videos(MediaType.SHOW, SERIES_ID, season=SEASON)
        second = get_videos(MediaType.SHOW, SERIES_ID, season=SEASON)
        assert mock_get.call_count == 1
        assert second == first

    def test_key_varies_by_type_id_season_and_language(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        get_videos(MediaType.SHOW, SERIES_ID)
        get_videos(MediaType.SHOW, SERIES_ID, season=SEASON)
        get_videos(MediaType.MOVIE, SERIES_ID)
        get_videos(MediaType.SHOW, SERIES_ID + 1)
        mocker.patch.object(tmdb.config, "target_language", "fr")
        get_videos(MediaType.SHOW, SERIES_ID)
        assert mock_get.call_count == 5

    def test_ttl_read_from_runtime_setting_at_write_time(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, VIDEOS_PAYLOAD)
        spy = mocker.spy(cache, "set")
        mocker.patch.object(tmdb.config, "discover_cache_seconds", OTHER_CACHE_TTL)
        get_videos(MediaType.MOVIE, MOVIE_ID)
        assert spy.call_args.kwargs["expire"] == OTHER_CACHE_TTL

    def test_failure_is_not_cached(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {}, status_code=HTTP_SERVER_ERROR)
        with pytest.raises(TmdbUnavailableError):
            get_videos(MediaType.MOVIE, MOVIE_ID)
        assert len(cache) == 0


class TestFailures:
    def test_missing_api_key_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", None)
        mock_get = _mock_get(mocker, VIDEOS_PAYLOAD)
        with pytest.raises(TmdbUnavailableError):
            get_videos(MediaType.MOVIE, MOVIE_ID)
        mock_get.assert_not_called()

    def test_network_error_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.requests, "get", side_effect=requests.ConnectionError("down"))
        with pytest.raises(TmdbUnavailableError):
            get_videos(MediaType.MOVIE, MOVIE_ID)
