"""Tests for platform registration state."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from upwork_scraper.config import ALL_PLATFORMS, ScraperConfig
from upwork_scraper.platforms.registry import (
    _ThreadLocalScraperPool,
    build_platform_adapters,
)


class PlatformRegistryTests(unittest.TestCase):
    def test_bark_is_temporarily_disabled(self) -> None:
        self.assertNotIn("bark", ALL_PLATFORMS)

        config = ScraperConfig(platforms=["bark"])
        adapters = build_platform_adapters(config)

        self.assertNotIn("bark", adapters)

    def test_keyword_worker_counts_match_platform_type(self) -> None:
        config = ScraperConfig(
            platforms=["upwork_selenium", "freelancer", "guru", "vollna"],
            upwork_keyword_workers=2,
            http_keyword_workers=3,
        )

        adapters = build_platform_adapters(config)
        try:
            self.assertEqual(
                adapters["upwork_selenium"].keyword_workers,
                2,
            )
            self.assertEqual(adapters["freelancer"].keyword_workers, 3)
            self.assertEqual(adapters["guru"].keyword_workers, 3)
            self.assertIsNotNone(adapters["vollna"].scrape_many_fn)
        finally:
            for adapter in adapters.values():
                adapter.close()

    def test_thread_local_pool_does_not_share_scraper_instances(self) -> None:
        created: list[object] = []
        barrier = Barrier(2)

        def factory() -> object:
            instance = object()
            created.append(instance)
            return instance

        pool = _ThreadLocalScraperPool(factory)

        def get_instance() -> object:
            instance = pool.get()
            barrier.wait()
            return instance

        with ThreadPoolExecutor(max_workers=2) as executor:
            instances = list(executor.map(lambda _: get_instance(), range(2)))

        self.assertEqual(len(created), 2)
        self.assertIsNot(instances[0], instances[1])


if __name__ == "__main__":
    unittest.main()
