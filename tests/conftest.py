"""Shared pytest fixtures for HTTP layer tests."""

import pytest
from fastapi.testclient import TestClient

from torrent_downloader.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
