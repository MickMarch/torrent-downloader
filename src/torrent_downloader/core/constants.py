"""Application-wide constants: OpenAPI tags and process start time for uptime tracking."""

import time

TAG_SYSTEM = "System"
TAG_SEARCH = "Search"
TAG_TRANSFERS = "Transfer Management"

API_START_TIME: float = time.time()
