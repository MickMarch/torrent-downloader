from typing import Any, Dict, List

from torrent_downloader.config import config
from torrent_downloader.search import filter_and_sort_results


def test_filter_and_sort_results() -> None:
    """Validates the seeder filtering and sorting logic."""

    TEST_MINIMUM_SEEDERS: int = 10
    config.minimum_seeders = TEST_MINIMUM_SEEDERS

    mock_results: List[Dict[str, Any]] = [
        {"fileName": "low_seeds", "nbSeeders": 5},
        {"fileName": "high_seeds", "nbSeeders": 50},
        {"fileName": "medium_seeds", "nbSeeders": 15},
    ]

    EXPECTED_RESULT_COUNT: int = 2
    EXPECTED_FIRST_RESULT_NAME: str = "high_seeds"

    filtered: List[Dict[str, Any]] = filter_and_sort_results(mock_results)

    assert len(filtered) == EXPECTED_RESULT_COUNT
    assert filtered[0].get("fileName") == EXPECTED_FIRST_RESULT_NAME
