"""Application-wide constants: OpenAPI tags, process start time for uptime
tracking, and the pick fallback policy."""

import time
from enum import Enum

TAG_SYSTEM = "System"
TAG_SEARCH = "Search"
TAG_TRANSFERS = "Transfer Management"
TAG_DISCOVER = "Discover"

API_START_TIME: float = time.time()


class PickFallback(str, Enum):
    LOWER = "lower"
    """Take the next lower resolution when the requested one has no candidate."""
    NONE = "none"
    """Only the requested resolution; otherwise nothing is picked."""
