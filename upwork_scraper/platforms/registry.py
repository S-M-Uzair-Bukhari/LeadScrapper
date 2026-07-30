"""Construct adapters around the existing platform scraper classes."""

from __future__ import annotations

from threading import Lock, local
from typing import Callable

# from ..bark_scraper import BarkScraper  # Temporarily disabled.
from ..config import ScraperConfig
from ..freelancer import FreelancerScraper
from ..guru import GuruScraper
from ..scraper import UpworkScraper
from ..selenium_scraper import UpworkSeleniumScraper
from ..vollna import VollnaScraper
from .base import PlatformAdapter


class _ThreadLocalScraperPool:
    """Create one non-shared scraper instance per keyword worker thread."""

    def __init__(self, factory: Callable[[], object]) -> None:
        self._factory = factory
        self._local = local()
        self._instances: list[object] = []
        self._lock = Lock()

    def get(self) -> object:
        instance = getattr(self._local, "instance", None)
        if instance is None:
            instance = self._factory()
            self._local.instance = instance
            with self._lock:
                self._instances.append(instance)
        return instance

    def close(self) -> None:
        with self._lock:
            instances = list(self._instances)
            self._instances.clear()
        for instance in instances:
            close = getattr(instance, "close", None)
            if close is not None:
                close()


def build_platform_adapters(config: ScraperConfig) -> dict[str, PlatformAdapter]:
    """Build enabled scraper instances without changing their core behavior."""
    adapters: dict[str, PlatformAdapter] = {}
    resolved_platforms = config.resolved_platforms

    if "upwork" in resolved_platforms:
        scraper = UpworkScraper(
            config,
            selenium_fallback="upwork_selenium" not in resolved_platforms,
        )
        adapters["upwork"] = PlatformAdapter(
            "upwork",
            scraper.search_keyword,
            scraper.close,
            resource_group=(
                "http"
                if "upwork_selenium" in resolved_platforms
                else "browser"
            ),
        )

    if "upwork_selenium" in resolved_platforms:
        pool = _ThreadLocalScraperPool(
            lambda: UpworkSeleniumScraper(config)
        )
        adapters["upwork_selenium"] = PlatformAdapter(
            "upwork_selenium",
            lambda keyword, worker_pool=pool: (
                worker_pool.get().search_keyword(keyword)
            ),
            pool.close,
            resource_group="browser",
            keyword_workers=config.upwork_keyword_workers,
        )

    if "vollna" in resolved_platforms:
        scraper = VollnaScraper(config)
        adapters["vollna"] = PlatformAdapter(
            "vollna",
            scraper.search_keyword,
            scraper.close,
            scrape_many_fn=scraper.search_keywords,
        )

    if "freelancer" in resolved_platforms:
        pool = _ThreadLocalScraperPool(FreelancerScraper)
        adapters["freelancer"] = PlatformAdapter(
            "freelancer",
            lambda keyword, worker_pool=pool: worker_pool.get().scrape(
                keyword,
                config.max_results_per_keyword,
                config.page_limit,
                config.collection_recency_hours,
            ),
            pool.close,
            keyword_workers=config.http_keyword_workers,
        )

    if "guru" in resolved_platforms:
        pool = _ThreadLocalScraperPool(GuruScraper)
        adapters["guru"] = PlatformAdapter(
            "guru",
            lambda keyword, worker_pool=pool: worker_pool.get().scrape(
                keyword,
                config.max_results_per_keyword,
                config.page_limit,
                config.collection_recency_hours,
            ),
            pool.close,
            keyword_workers=config.http_keyword_workers,
        )

    # Bark is temporarily disabled. Keep this registration block intact so it
    # can be restored together with the ALL_PLATFORMS entry in config.py.
    #
    # if "bark" in config.resolved_platforms:
    #     scraper = BarkScraper(config)
    #     adapters["bark"] = PlatformAdapter(
    #         "bark",
    #         scraper.search_keyword,
    #         scraper.close,
    #         resource_group="browser",
    #     )

    return adapters
