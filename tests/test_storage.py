"""Tests for storage service: get_disk_usage pure logic."""

import shutil
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from torrent_downloader.services.storage import BYTES_PER_GB, get_disk_usage

_UsageType = type(shutil.disk_usage("."))


def make_usage(total_gb: float, used_gb: float) -> object:
    total = int(total_gb * BYTES_PER_GB)
    used = int(used_gb * BYTES_PER_GB)
    free = total - used
    return _UsageType(total, used, free)


# ---------------------------------------------------------------------------
# get_disk_usage
# ---------------------------------------------------------------------------

class TestGetDiskUsage:
    def test_returns_total_gb(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.storage.shutil.disk_usage", return_value=make_usage(500, 200))
        assert get_disk_usage(str(tmp_path))["total_gb"] == 500.0

    def test_returns_used_gb(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.storage.shutil.disk_usage", return_value=make_usage(500, 200))
        assert get_disk_usage(str(tmp_path))["used_gb"] == 200.0

    def test_returns_free_gb(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.storage.shutil.disk_usage", return_value=make_usage(500, 200))
        assert get_disk_usage(str(tmp_path))["free_gb"] == 300.0

    def test_returns_used_percent(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.services.storage.shutil.disk_usage", return_value=make_usage(500, 250))
        assert get_disk_usage(str(tmp_path))["used_percent"] == 50.0

    def test_passes_path_object_to_disk_usage(self, tmp_path: Path, mocker: MockerFixture) -> None:
        spy = mocker.patch("torrent_downloader.services.storage.shutil.disk_usage", return_value=make_usage(100, 50))
        get_disk_usage(str(tmp_path))
        assert isinstance(spy.call_args[0][0], Path)

    def test_raises_on_nonexistent_path(self) -> None:
        with pytest.raises((FileNotFoundError, OSError)):
            get_disk_usage("/nonexistent/path/xyz_does_not_exist")
