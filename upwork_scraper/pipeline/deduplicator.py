"""Thread-safe run-level lead deduplication."""

from __future__ import annotations

import re
from threading import Lock

from ..models import JobLead


class RunDeduplicator:
    """Preserve the current title-based deduplication across platform workers."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = Lock()

    @staticmethod
    def key(lead: JobLead) -> str:
        return re.sub(r"\s+", " ", lead.title).strip().casefold()

    def accept(self, lead: JobLead) -> bool:
        key = self.key(lead)
        if not key:
            return False
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True
