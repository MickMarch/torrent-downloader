"""HTTP layer tests for GET /api/v1/search/torrents."""

from typing import Any

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

SEARCH_URL = "/api/v1/search/torrents"


def _make_torrent(name: str, seeders: int, url: str) -> dict[str, Any]:
    return {
        "fileName": name,
        "fileUrl": url,
        "nbSeeders": seeders,
        "nbLeechers": 5,
        "siteUrl": "https://example.com",
        "descrLink": "https://example.com/desc",
        "fileSize": 10_000_000_000,
    }


MOCK_FILTERED_RESULTS: list[dict[str, Any]] = [
    _make_torrent("Inception.2010.2160p.BluRay.x265", 100, "magnet:?xt=urn:btih:aaa"),
    _make_torrent("Inception.2010.1080p.WEB-DL.x264", 80, "magnet:?xt=urn:btih:bbb"),
    _make_torrent("Inception.2010.720p.HDTV.x264", 30, "magnet:?xt=urn:btih:ccc"),
]


MOVIE_PARAMS = {"query": "inception", "media_type": "movie"}


def _patch_pipeline(mocker: MockerFixture, results: list[dict[str, Any]]) -> None:
    mocker.patch(
        "torrent_downloader.routers.search.get_torrent_client", return_value=mocker.MagicMock()
    )
    mocker.patch("torrent_downloader.routers.search.run_pattern_searches", return_value={})
    mocker.patch("torrent_downloader.routers.search.search_torrents", return_value=results)
    mocker.patch("torrent_downloader.routers.search.filter_and_sort_results", return_value=results)


class TestSearchTorrentsRoute:
    def test_returns_503_when_client_unavailable(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.get_torrent_client", return_value=None)
        response = client.get(SEARCH_URL, params=MOVIE_PARAMS)
        assert response.status_code == 503

    def test_returns_200_with_valid_client(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(SEARCH_URL, params=MOVIE_PARAMS)
        assert response.status_code == 200

    def test_response_shape_has_status_message_data(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        body = client.get(SEARCH_URL, params=MOVIE_PARAMS).json()
        assert "status" in body
        assert "message" in body
        assert "data" in body

    def test_results_grouped_by_resolution_keys(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        data = client.get(SEARCH_URL, params=MOVIE_PARAMS).json()["data"]
        for key in data:
            assert key in ("4K", "1080p", "720p")

    def test_returns_empty_data_when_no_results(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [])
        body = client.get(SEARCH_URL, params={"query": "xyzzy", "media_type": "movie"}).json()
        assert body["data"] == {}

    def test_requires_query_param(self, client: TestClient) -> None:
        response = client.get(SEARCH_URL, params={"media_type": "movie"})
        assert response.status_code == 422

    def test_requires_media_type_param(self, client: TestClient) -> None:
        response = client.get(SEARCH_URL, params={"query": "inception"})
        assert response.status_code == 422

    def test_movie_with_season_is_rejected(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(
            SEARCH_URL, params={"query": "inception", "media_type": "movie", "season": 1}
        )
        assert response.status_code == 422

    def test_orphan_episode_is_rejected(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(
            SEARCH_URL, params={"query": "show", "media_type": "show", "episode": 3}
        )
        assert response.status_code == 422

    def test_show_season_search_threads_scope_into_filter(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        spy = mocker.patch(
            "torrent_downloader.routers.search.filter_by_scope",
            return_value=MOCK_FILTERED_RESULTS,
        )
        response = client.get(
            SEARCH_URL, params={"query": "the wire", "media_type": "show", "season": 2}
        )
        assert response.status_code == 200
        scope_arg = spy.call_args.args[1]
        assert scope_arg.season == 2
        assert scope_arg.episode is None


class TestMovieBareTitlePass:
    def test_year_and_bare_title_are_both_searched_and_unioned(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_torrent_client",
            return_value=mocker.MagicMock(),
        )
        mocker.patch("torrent_downloader.routers.search.run_pattern_searches", return_value={})
        by_query = {
            "Storks 2016": [
                _make_torrent("Storks.2016.2160p.WEB.x265", 95, "magnet:?xt=urn:btih:ccc"),
                _make_torrent("Storks.2016.1080p.BluRay.x264", 90, "magnet:?xt=urn:btih:aaa"),
            ],
            "Storks": [
                _make_torrent("Storks.2016.1080p.BluRay.x264", 90, "magnet:?xt=urn:btih:aaa"),
                _make_torrent("Storks.2019.720p.WEB.x264", 90, "magnet:?xt=urn:btih:bbb"),
            ],
        }
        search = mocker.patch(
            "torrent_downloader.routers.search.search_torrents",
            side_effect=lambda _c, q, _s: by_query[q],
        )
        body = client.get(SEARCH_URL, params={"query": "Storks 2016", "media_type": "movie"}).json()
        assert [c.args[1] for c in search.call_args_list] == ["Storks 2016", "Storks"]
        names = [t["fileName"] for group in body["data"].values() for t in group]
        assert sorted(names) == ["Storks.2016.1080p.BluRay.x264", "Storks.2016.2160p.WEB.x265"]

    def test_no_second_pass_without_a_trailing_year(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [])
        search = mocker.patch("torrent_downloader.routers.search.search_torrents", return_value=[])
        client.get(SEARCH_URL, params={"query": "Storks", "media_type": "movie"})
        assert search.call_count == 1


class TestAltQuery:
    def test_alt_query_is_searched_and_unioned(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_torrent_client",
            return_value=mocker.MagicMock(),
        )
        mocker.patch("torrent_downloader.routers.search.run_pattern_searches", return_value={})
        by_query = {
            "Lee Cronin's The Mummy 2026": [
                _make_torrent("Lee.Cronins.The.Mummy.2026.1080p", 40, "magnet:?xt=urn:btih:aaa")
            ],
            "Lee Cronin's The Mummy": [],
            "The Mummy 2026": [
                _make_torrent("The.Mummy.2026.2160p.WEB", 90, "magnet:?xt=urn:btih:bbb"),
                _make_torrent("Lee.Cronins.The.Mummy.2026.1080p", 40, "magnet:?xt=urn:btih:aaa"),
            ],
            "The Mummy": [_make_torrent("The.Mummy.1999.1080p", 500, "magnet:?xt=urn:btih:old")],
        }
        search = mocker.patch(
            "torrent_downloader.routers.search.search_torrents",
            side_effect=lambda _c, q, _s: by_query[q],
        )
        body = client.get(
            SEARCH_URL,
            params={
                "query": "Lee Cronin's The Mummy 2026",
                "media_type": "movie",
                "alt_query": "The Mummy 2026",
            },
        ).json()
        assert [c.args[1] for c in search.call_args_list] == list(by_query)
        names = sorted(t["fileName"] for group in body["data"].values() for t in group)
        assert names == ["Lee.Cronins.The.Mummy.2026.1080p", "The.Mummy.2026.2160p.WEB"]

    def test_alt_query_equal_to_query_is_not_searched_twice(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [])
        search = mocker.patch("torrent_downloader.routers.search.search_torrents", return_value=[])
        client.get(
            SEARCH_URL,
            params={"query": "The Wire", "media_type": "show", "alt_query": "the wire "},
        )
        assert search.call_count == 1


class TestPrefetch:
    def test_every_pattern_of_every_query_is_prefetched_once(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_torrent_client",
            return_value=mocker.MagicMock(),
        )
        prefetch = mocker.patch(
            "torrent_downloader.routers.search.run_pattern_searches", return_value={}
        )
        mocker.patch("torrent_downloader.routers.search.search_torrents", return_value=[])
        client.get(
            SEARCH_URL,
            params={"query": "Storks 2016", "media_type": "movie", "alt_query": "The Storks 2016"},
        )
        prefetch.assert_called_once()
        assert prefetch.call_args.args[1] == [
            "Storks 2016",
            "Storks",
            "The Storks 2016",
            "The Storks",
        ]
        assert prefetch.call_args.args[2] == "movies"
