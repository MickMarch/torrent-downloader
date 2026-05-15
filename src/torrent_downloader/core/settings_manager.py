import os
from typing import Any, Dict

from dotenv import set_key

from torrent_downloader.core.config import config


def update_environment_variables(updates: Dict[str, Any]) -> None:
    """Writes configuration modifications to the configured environment file."""
    env_file_path: str = str(config.model_config.get("env_file", ".env"))

    if not os.path.exists(env_file_path):
        open(env_file_path, "a", encoding="utf-8").close()

    for key, value in updates.items():
        env_key: str = key.upper()
        set_key(env_file_path, env_key, str(value))
