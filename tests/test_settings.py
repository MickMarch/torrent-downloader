"""Runtime settings: registry, store, live application onto config, routes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from medialab_contracts import SettingSource

from torrent_downloader.core import settings as settings_module
from torrent_downloader.core.config import AppConfig
from torrent_downloader.core.settings import (
    SETTINGS,
    RuntimeSettings,
    SettingsStore,
    UnknownSettingError,
)
from torrent_downloader.services.language import LanguageFilter


def _runtime(tmp_path: Path, **env) -> tuple[AppConfig, RuntimeSettings, Path]:
    cfg = AppConfig(_env_file=None, **env)
    path = tmp_path / "settings.json"
    return cfg, RuntimeSettings(cfg, SettingsStore(path)), path


class TestRegistry:
    def test_declared_keys_only(self, tmp_path: Path) -> None:
        _, rt, _ = _runtime(tmp_path)
        assert [v.key for v in rt.views()] == [s.key for s in SETTINGS]
        with pytest.raises(UnknownSettingError):
            rt.view("api_key")
        with pytest.raises(UnknownSettingError):
            rt.set("qb_api_key", "x")

    def test_source_reports_default_env_and_override(self, tmp_path: Path) -> None:
        cfg, rt, _ = _runtime(tmp_path, minimum_seeders=25)
        assert rt.view("minimum_seeders").source is SettingSource.ENV
        assert rt.view("search_timeout_seconds").source is SettingSource.DEFAULT
        rt.set("search_timeout_seconds", 30)
        assert rt.view("search_timeout_seconds").source is SettingSource.OVERRIDE
        assert rt.view("search_timeout_seconds").default == 15


class TestApply:
    def test_set_applies_to_config_and_persists(self, tmp_path: Path) -> None:
        cfg, rt, path = _runtime(tmp_path)
        view = rt.set("minimum_seeders", "3")
        assert view.value == 3
        assert cfg.minimum_seeders == 3
        assert json.loads(path.read_text())["minimum_seeders"] == 3

    def test_enum_field_gets_the_member(self, tmp_path: Path) -> None:
        cfg, rt, _ = _runtime(tmp_path)
        rt.set("audio_language_filter", "STRICT")
        assert cfg.audio_language_filter is LanguageFilter.STRICT
        assert rt.view("audio_language_filter").value == "strict"

    def test_bounds_are_enforced_and_nothing_changes(self, tmp_path: Path) -> None:
        cfg, rt, path = _runtime(tmp_path)
        with pytest.raises(ValueError, match="at most"):
            rt.set("search_concurrency", 9)
        assert cfg.search_concurrency == 4
        assert not path.exists()

    def test_reset_restores_the_env_value(self, tmp_path: Path) -> None:
        cfg, rt, path = _runtime(tmp_path, minimum_seeders=25)
        rt.set("minimum_seeders", 1)
        view = rt.reset("minimum_seeders")
        assert cfg.minimum_seeders == 25
        assert view.source is SettingSource.ENV
        assert json.loads(path.read_text()) == {}

    def test_overrides_survive_a_restart(self, tmp_path: Path) -> None:
        _, rt, path = _runtime(tmp_path)
        rt.set("target_language", "fr")
        cfg2 = AppConfig(_env_file=None)
        RuntimeSettings(cfg2, SettingsStore(path))
        assert cfg2.target_language == "fr"

    def test_bad_store_entries_are_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"minimum_seeders": "lots", "nope": 1, "search_concurrency": 2}))
        cfg = AppConfig(_env_file=None)
        RuntimeSettings(cfg, SettingsStore(path))
        assert cfg.minimum_seeders == 10
        assert cfg.search_concurrency == 2

    def test_unreadable_store_means_no_overrides(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{not json")
        assert SettingsStore(path).load() == {}


class TestRoutes:
    @pytest.fixture(autouse=True)
    def _isolated_runtime(self, tmp_path: Path, mocker) -> None:
        cfg, rt, _ = _runtime(tmp_path)
        mocker.patch.object(settings_module, "runtime_settings", rt)
        mocker.patch("torrent_downloader.routers.settings.runtime_settings", rt)

    def test_list(self, client: TestClient) -> None:
        body = client.get("/api/v1/settings").json()
        assert body["status"] == "success"
        keys = [s["key"] for s in body["settings"]]
        assert "minimum_seeders" in keys and "api_key" not in keys
        choice = next(s for s in body["settings"] if s["key"] == "audio_language_filter")
        assert choice["choices"] == ["lenient", "strict", "off"]

    def test_put_then_delete(self, client: TestClient) -> None:
        resp = client.put("/api/v1/settings/minimum_seeders", json={"value": 2})
        assert resp.status_code == 200
        assert resp.json()["value"] == 2 and resp.json()["source"] == "override"
        resp = client.delete("/api/v1/settings/minimum_seeders")
        assert resp.status_code == 200
        assert resp.json()["source"] == "default"

    def test_out_of_bounds_is_422(self, client: TestClient) -> None:
        resp = client.put("/api/v1/settings/search_timeout_seconds", json={"value": 1})
        assert resp.status_code == 422
        assert "at least" in resp.json()["detail"]

    def test_unknown_key_is_404(self, client: TestClient) -> None:
        assert client.put("/api/v1/settings/api_key", json={"value": "x"}).status_code == 404
        assert client.delete("/api/v1/settings/nope").status_code == 404

    def test_requires_api_key(self) -> None:
        from torrent_downloader.main import app

        assert TestClient(app).get("/api/v1/settings").status_code == 403
