"""Tests for platform registration state."""

import unittest

from upwork_scraper.config import ALL_PLATFORMS, ScraperConfig
from upwork_scraper.platforms.registry import build_platform_adapters


class PlatformRegistryTests(unittest.TestCase):
    def test_bark_is_temporarily_disabled(self) -> None:
        self.assertNotIn("bark", ALL_PLATFORMS)

        config = ScraperConfig(platforms=["bark"])
        adapters = build_platform_adapters(config)

        self.assertNotIn("bark", adapters)


if __name__ == "__main__":
    unittest.main()
