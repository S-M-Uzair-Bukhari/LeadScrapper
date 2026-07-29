"""Common interface for existing platform scrapers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import JobLead


@dataclass
class PlatformAdapter:
    """Adapt a platform-specific scraper to one orchestration interface."""

    name: str
    scrape_fn: Callable[[str], list[JobLead]]
    close_fn: Callable[[], None] | None = None
    resource_group: str = "http"

    def scrape(self, keyword: str) -> list[JobLead]:
        return self.scrape_fn(keyword)

    def close(self) -> None:
        if self.close_fn is not None:
            self.close_fn()
