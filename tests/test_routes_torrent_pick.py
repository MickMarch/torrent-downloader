"""HTTP layer tests for GET /api/v1/search/torrents/pick."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from torrent_downloader.core.config import config
from torrent_downloader.core.errors import ErrorCode

PICK_URL = "/api/v1/search/torrents/pick"
SEARCH_ROUTER = "torrent_downloader.routers.search"

EPISODE_PARAMS = {"query": "the wire", "season": 2, "episode": 5, "resolution": "1080p"}


def _make_torrent(name: str, seeders: int, url: str) -> dict[str, Any]:
    return {
        "fileName": name,
        "fileUrl": url,
        "nbSeeders": seeders,
        "nbLeechers": 5,
        "siteUrl": "https://example.com",
        "descrLink": "https://example.com/desc",
        "fileSize": 2_000_000_000,
    }


EXACT_1080 = _make_torrent("The.Wire.S02E05.1080p.WEB", 80, "magnet:?xt=urn:btih:aaa")
EXACT_720 = _make_torrent("The.Wire.S02E05.720p.WEB", 30, "magnet:?xt=urn:btih:bbb")
SEASON_PACK = _make_torrent("The.Wire.S02.1080p.BluRay", 900, "magnet:?xt=urn:btih:ccc")

MOCK_RESULTS: list[dict[str, Any]] = [SEASON_PACK, EXACT_1080, EXACT_720]


def _patch_pipeline(mocker: MockerFixture, results: list[dict[str, Any]]) -> None:
    mocker.patch(f"{SEARCH_ROUTER}.get_torrent_client", return_value=mocker.MagicMock())
    mocker.patch(f"{SEARCH_ROUTER}.run_pattern_searches", return_value={})
    mocker.patch(f"{SEARCH_ROUTER}.search_torrents", return_value=results)
    mocker.patch(f"{SEARCH_ROUTER}.filter_and_sort_results", return_value=results)


@pytest.fixture
def unauthed_client() -> TestClient:
    from torrent_downloader.main import app

    return TestClient(app, raise_server_exceptions=False)


class TestPickRoute:
    def test_returns_one_torrent_result(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 200
        body = response.json()
        assert body["fileName"] == EXACT_1080["fileName"]
        assert body["fileUrl"] == EXACT_1080["fileUrl"]
        assert body["nbSeeders"] == EXACT_1080["nbSeeders"]
        assert "languages" in body
        assert "multiAudio" in body

    def test_falls_back_one_bucket_lower(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, [SEASON_PACK, EXACT_720])
        body = client.get(PICK_URL, params=EPISODE_PARAMS).json()
        assert body["fileName"] == EXACT_720["fileName"]

    def test_returns_404_no_candidate_when_nothing_qualifies(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [SEASON_PACK])
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NO_CANDIDATE.value

    def test_returns_404_no_candidate_when_search_is_empty(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [])
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NO_CANDIDATE.value

    def test_searches_the_episode_scope_as_a_show(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        spy = mocker.patch(f"{SEARCH_ROUTER}.filter_by_scope", return_value=MOCK_RESULTS)
        client.get(PICK_URL, params=EPISODE_PARAMS)
        scope_arg = spy.call_args.args[1]
        assert scope_arg.media_type.value == "show"
        assert scope_arg.season == 2
        assert scope_arg.episode == 5

    def test_alt_query_is_searched_too(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        search = mocker.patch(f"{SEARCH_ROUTER}.search_torrents", return_value=MOCK_RESULTS)
        client.get(PICK_URL, params={**EPISODE_PARAMS, "alt_query": "wire"})
        assert [c.args[1] for c in search.call_args_list] == ["the wire", "wire"]

    def test_returns_503_when_client_unavailable(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(f"{SEARCH_ROUTER}.get_torrent_client", return_value=None)
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 503
        assert response.json()["code"] == ErrorCode.QB_UNAVAILABLE.value


class TestPickValidation:
    def test_season_only_picks_the_pack(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        params = {k: v for k, v in EPISODE_PARAMS.items() if k != "episode"}
        response = client.get(PICK_URL, params=params)
        assert response.status_code == 200
        assert response.json()["fileName"] == SEASON_PACK["fileName"]

    def test_season_only_searches_the_season_scope(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        search = mocker.patch(f"{SEARCH_ROUTER}.search_torrents", return_value=MOCK_RESULTS)
        params = {k: v for k, v in EPISODE_PARAMS.items() if k != "episode"}
        client.get(PICK_URL, params=params)
        scope = search.call_args.args[2]
        assert (scope.season, scope.episode) == (2, None)

    def test_timeout_override_is_active_during_the_search_and_cleared_after(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        from torrent_downloader.services import qbittorrent as qb

        seen: list[int | None] = []

        def capture(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            seen.append(qb.search_timeout_override.get())
            return MOCK_RESULTS

        _patch_pipeline(mocker, MOCK_RESULTS)
        mocker.patch(f"{SEARCH_ROUTER}.search_torrents", side_effect=capture)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "timeout_seconds": 90})
        assert response.status_code == 200
        assert seen and seen[0] == 90
        assert qb.search_timeout_override.get() is None

    def test_timeout_outside_the_setting_bounds_is_422(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        for value in (1, 10_000):
            response = client.get(PICK_URL, params={**EPISODE_PARAMS, "timeout_seconds": value})
            assert response.status_code == 422, value

    def test_missing_episode_is_422_for_a_movie_style_request(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        # Without a season there is no show scope at all.
        _patch_pipeline(mocker, MOCK_RESULTS)
        params = {k: v for k, v in EPISODE_PARAMS.items() if k not in ("episode", "season")}
        assert client.get(PICK_URL, params=params).status_code == 422

    def test_missing_season_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        params = {k: v for k, v in EPISODE_PARAMS.items() if k != "season"}
        assert client.get(PICK_URL, params=params).status_code == 422

    def test_missing_resolution_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        params = {k: v for k, v in EPISODE_PARAMS.items() if k != "resolution"}
        assert client.get(PICK_URL, params=params).status_code == 422

    def test_other_resolution_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "resolution": "Other"})
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_INPUT.value

    def test_unknown_resolution_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "resolution": "8K"})
        assert response.status_code == 422

    def test_zero_season_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "season": 0})
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_INPUT.value

    def test_negative_min_seeders_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "min_seeders": -1})
        assert response.status_code == 422


class TestPickSeederFloor:
    def test_explicit_min_seeders_is_applied(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        response = client.get(PICK_URL, params={**EPISODE_PARAMS, "min_seeders": 81})
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NO_CANDIDATE.value

    def test_min_seeders_defaults_to_config(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        mocker.patch.object(config, "minimum_seeders", 81)
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NO_CANDIDATE.value

    def test_config_floor_at_result_seeders_keeps_it(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_RESULTS)
        mocker.patch.object(config, "minimum_seeders", EXACT_1080["nbSeeders"])
        response = client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 200
        assert response.json()["fileName"] == EXACT_1080["fileName"]


class TestPickAuth:
    def test_missing_key_is_403(self, unauthed_client: TestClient) -> None:
        response = unauthed_client.get(PICK_URL, params=EPISODE_PARAMS)
        assert response.status_code == 403
        assert response.json()["code"] == ErrorCode.UNAUTHORIZED.value
