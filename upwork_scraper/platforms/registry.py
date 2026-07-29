"""Construct adapters around the existing platform scraper classes."""

from __future__ import annotations

from ..bark_scraper import BarkScraper
from ..config import ScraperConfig
from ..freelancer import FreelancerScraper
from ..guru import GuruScraper
from ..scraper import UpworkScraper
from ..selenium_scraper import UpworkSeleniumScraper
from ..vollna import VollnaScraper
from .base import PlatformAdapter


def build_platform_adapters(config: ScraperConfig) -> dict[str, PlatformAdapter]:
    """Build enabled scraper instances without changing their core behavior."""
    adapters: dict[str, PlatformAdapter] = {}

    if "upwork" in config.resolved_platforms:
        scraper = UpworkScraper(config)
        adapters["upwork"] = PlatformAdapter(
            "upwork",
            scraper.search_keyword,
            scraper.close,
            resource_group="browser",
        )

    if "upwork_selenium" in config.resolved_platforms:
        scraper = UpworkSeleniumScraper(config)
        adapters["upwork_selenium"] = PlatformAdapter(
            "upwork_selenium",
            scraper.search_keyword,
            scraper.close,
            resource_group="browser",
        )

    if "vollna" in config.resolved_platforms:
        scraper = VollnaScraper(config)
        adapters["vollna"] = PlatformAdapter(
            "vollna", scraper.search_keyword, scraper.close
        )

    if "freelancer" in config.resolved_platforms:
        scraper = FreelancerScraper()
        adapters["freelancer"] = PlatformAdapter(
            "freelancer",
            lambda keyword, instance=scraper: instance.scrape(
                keyword, config.max_results_per_keyword
            ),
            getattr(scraper, "close", None),
        )

    if "guru" in config.resolved_platforms:
        scraper = GuruScraper()
        adapters["guru"] = PlatformAdapter(
            "guru",
            lambda keyword, instance=scraper: instance.scrape(
                keyword, config.max_results_per_keyword
            ),
            getattr(scraper, "close", None),
        )

    if "bark" in config.resolved_platforms:
        scraper = BarkScraper(config)
        adapters["bark"] = PlatformAdapter(
            "bark",
            scraper.search_keyword,
            scraper.close,
            resource_group="browser",
        )

    return adapters
