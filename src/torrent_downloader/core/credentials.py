"""Per-credential health this service owns: the TMDB key and the qBittorrent WebUI key.

Every upstream call classifies its outcome here at no extra traffic (a refusal
marks the credential invalid, a success marks it ok, a transport failure marks
it unreachable), and a slow probe covers keys that expire while idle. The map
is exposed on the health response for the orchestrator to aggregate.
"""

import threading
from datetime import UTC, datetime

from medialab_contracts import (
    CREDENTIAL_QB_API_KEY,
    CREDENTIAL_TMDB_API_KEY,
    CredentialState,
    CredentialStatus,
)

OWNED_CREDENTIALS: tuple[str, ...] = (CREDENTIAL_TMDB_API_KEY, CREDENTIAL_QB_API_KEY)


class CredentialTracker:
    def __init__(self, names: tuple[str, ...] = OWNED_CREDENTIALS) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, CredentialState] = {name: CredentialState() for name in names}

    def _set(self, name: str, status: CredentialStatus, detail: str) -> None:
        with self._lock:
            self._states[name] = CredentialState(
                status=status, checked_at=datetime.now(UTC), detail=detail
            )

    def mark_ok(self, name: str) -> None:
        self._set(name, CredentialStatus.OK, "")

    def mark_invalid(self, name: str, detail: str) -> None:
        self._set(name, CredentialStatus.INVALID, detail)

    def mark_unreachable(self, name: str, detail: str) -> None:
        self._set(name, CredentialStatus.UNREACHABLE, detail)

    def snapshot(self) -> dict[str, CredentialState]:
        with self._lock:
            return dict(self._states)

    def reset(self) -> None:
        with self._lock:
            for name in self._states:
                self._states[name] = CredentialState()


credentials = CredentialTracker()
