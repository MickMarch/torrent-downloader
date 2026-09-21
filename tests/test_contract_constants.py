"""The app mounts under the shared API prefix and reads the shared key header."""

from medialab_contracts import (
    API_KEY_HEADER,
    API_PREFIX,
    HEALTH_PATH,
    MEDIA_TYPE_SUBDIRS,
    MediaType,
)

from torrent_downloader.main import app
from torrent_downloader.routers.transfers import _resolve_host_path


def test_every_route_is_under_the_shared_prefix() -> None:
    api_paths = list(app.openapi()["paths"])
    assert api_paths
    assert all(p.startswith(API_PREFIX) for p in api_paths)
    assert HEALTH_PATH in api_paths


def test_openapi_security_scheme_uses_the_shared_header() -> None:
    schemes = app.openapi()["components"]["securitySchemes"]
    assert any(s.get("name") == API_KEY_HEADER for s in schemes.values())


def test_host_path_uses_the_shared_subdir_map(mocker) -> None:
    mocker.patch("torrent_downloader.routers.transfers.config.media_host_path", r"F:\Media")
    for media_type in MediaType:
        assert _resolve_host_path(media_type).endswith(MEDIA_TYPE_SUBDIRS[media_type])
