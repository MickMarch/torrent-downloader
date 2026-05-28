"""Storage service: disk usage checks for configured save paths."""

import shutil
from pathlib import Path

from torrent_downloader.core.logger import app_logger

BYTES_PER_GB: float = 1024**3


def get_disk_usage(path: str) -> dict[str, float]:
    """Return total, used, and free disk space in GB for the given path."""
    try:
        usage = shutil.disk_usage(Path(path))
    except (FileNotFoundError, PermissionError, OSError) as error:
        app_logger.error(f"Disk usage check failed for path '{path}': {error}")
        raise

    return {
        "total_gb": round(usage.total / BYTES_PER_GB, 2),
        "used_gb": round(usage.used / BYTES_PER_GB, 2),
        "free_gb": round(usage.free / BYTES_PER_GB, 2),
        "used_percent": round((usage.used / usage.total) * 100, 2),
    }
