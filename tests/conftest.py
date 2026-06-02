"""Shared pytest fixtures for HTTP layer tests."""

import pytest
from fastapi.testclient import TestClient

from torrent_downloader.core.limiter import limiter
from torrent_downloader.main import app

TEST_API_KEY = "test-api-key"


@pytest.fixture(autouse=True)
def patch_api_key(mocker):
    mocker.patch("torrent_downloader.core.auth.config", api_key=TEST_API_KEY)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})
