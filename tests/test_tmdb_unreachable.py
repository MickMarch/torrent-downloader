"""TMDB unreachable (DNS failure, timeout): a typed error, never an empty result.

An empty list or dict reads as "no match"; a transport failure is not that.
The routes map the typed error to 503 TMDB_UNAVAILABLE so callers can retry.
"""

import pytest
import requests
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from torrent_downloader.core.errors import ErrorCode
from torrent_downloader.services.tmdb import (
    TmdbUnavailableError,
    get_movie_details,
    get_tv_details,
    search_tmdb_multi,
)

_DNS_FAILURE = requests.ConnectionError("Failed to resolve 'api.themoviedb.org'")


@pytest.fixture(autouse=True)
def tmdb_configured(mocker: MockerFixture):
    mocker.patch(
        "torrent_downloader.services.tmdb.config", tmdb_api_key="key", target_language="en-US"
    )
    from torrent_downloader.core.cache import app_cache

    app_cache.clear()
    yield
    app_cache.clear()


class TestServiceRaisesTyped:
    def test_search_raises_on_transport_failure(self, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.tmdb.requests.get", side_effect=_DNS_FAILURE)
        with pytest.raises(TmdbUnavailableError):
            search_tmdb_multi("inception")

    def test_movie_details_raise_on_transport_failure(self, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.tmdb.requests.get", side_effect=_DNS_FAILURE)
        with pytest.raises(TmdbUnavailableError):
            get_movie_details(27205)

    def test_tv_details_raise_on_transport_failure(self, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.tmdb.requests.get", side_effect=_DNS_FAILURE)
        with pytest.raises(TmdbUnavailableError):
            get_tv_details(1396)

    def test_search_passes_a_timeout(self, mocker: MockerFixture) -> None:
        # A hung TMDB must not hang the request thread.
        get = mocker.patch(
            "torrent_downloader.services.tmdb.requests.get",
            return_value=mocker.MagicMock(status_code=200, json=lambda: {"results": []}),
        )
        search_tmdb_multi("inception")
        assert get.call_args.kwargs.get("timeout")


class TestRoutesMapTo503:
    @pytest.mark.parametrize(
        "patched, path",
        [
            ("search_tmdb_multi", "/api/v1/search/tmdb?query=inception"),
            ("get_movie_details", "/api/v1/search/tmdb/movie/27205"),
            ("get_tv_details", "/api/v1/search/tmdb/show/1396"),
        ],
    )
    def test_unavailable_is_503(
        self, client: TestClient, mocker: MockerFixture, patched: str, path: str
    ) -> None:
        mocker.patch(
            f"torrent_downloader.routers.search.{patched}",
            side_effect=TmdbUnavailableError("TMDB request failed"),
        )
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["code"] == ErrorCode.TMDB_UNAVAILABLE.value
