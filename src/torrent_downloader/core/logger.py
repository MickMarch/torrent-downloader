import logging
import sys
from pathlib import Path

LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d - %(message)s"
)
DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
LOG_FILE_NAME: str = "torrent_downloader.log"
DOCUMENTS_DIR: Path = Path.home() / "Documents"
FULL_LOG_FILE_PATH: Path = DOCUMENTS_DIR / LOG_FILE_NAME


def setup_logger() -> logging.Logger:
    """Configures the root logger with both console and file output."""
    logger: logging.Logger = logging.getLogger("torrent_downloader")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter: logging.Formatter = logging.Formatter(
            fmt=LOG_FORMAT, datefmt=DATE_FORMAT
        )

        console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        file_handler: logging.FileHandler = logging.FileHandler(FULL_LOG_FILE_PATH)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


app_logger: logging.Logger = setup_logger()
