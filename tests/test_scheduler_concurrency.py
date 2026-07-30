from __future__ import annotations

import threading
import time
import unittest

from upwork_scraper.models import JobLead
from upwork_scraper.orchestration.events import KeywordResult
from upwork_scraper.orchestration.scheduler import PlatformScheduler
from upwork_scraper.platforms.base import PlatformAdapter


class SchedulerConcurrencyTests(unittest.TestCase):
    def test_keyword_workers_run_concurrently_within_platform(self) -> None:
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def scrape(keyword: str) -> list[JobLead]:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return [JobLead(title=keyword)]

        scheduler = PlatformScheduler(
            adapters={
                "test": PlatformAdapter(
                    "test",
                    scrape,
                    keyword_workers=2,
                )
            },
            keywords=["one", "two", "three", "four"],
            max_workers=1,
            max_browser_workers=2,
            queue_size=10,
        )

        results = [
            event
            for event in scheduler.events()
            if isinstance(event, KeywordResult)
        ]

        self.assertEqual(len(results), 4)
        self.assertEqual(maximum_active, 2)

    def test_global_browser_limit_applies_to_keyword_workers(self) -> None:
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def scrape(keyword: str) -> list[JobLead]:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return [JobLead(title=keyword)]

        adapters = {
            name: PlatformAdapter(
                name,
                scrape,
                resource_group="browser",
                keyword_workers=2,
            )
            for name in ("browser-a", "browser-b")
        }
        scheduler = PlatformScheduler(
            adapters=adapters,
            keywords=["one", "two", "three"],
            max_workers=2,
            max_browser_workers=2,
            queue_size=20,
        )

        list(scheduler.events())

        self.assertEqual(maximum_active, 2)

    def test_lead_processing_callback_runs_in_keyword_workers(self) -> None:
        processing_threads: list[str] = []

        def scrape(keyword: str) -> list[JobLead]:
            return [JobLead(title=keyword)]

        def process(_: str, __: str, leads: list[JobLead]) -> int:
            processing_threads.append(threading.current_thread().name)
            return len(leads)

        scheduler = PlatformScheduler(
            adapters={
                "test": PlatformAdapter(
                    "test",
                    scrape,
                    keyword_workers=2,
                )
            },
            keywords=["one", "two"],
            max_workers=1,
            max_browser_workers=1,
            queue_size=10,
            process_leads=process,
        )

        results = [
            event
            for event in scheduler.events()
            if isinstance(event, KeywordResult)
        ]

        self.assertEqual([event.qualified_count for event in results], [1, 1])
        self.assertTrue(
            all("test-keyword" in name for name in processing_threads)
        )


if __name__ == "__main__":
    unittest.main()
