"""Bounded platform-level concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import BoundedSemaphore
from typing import Iterator

from ..platforms.base import PlatformAdapter
from .events import KeywordResult, PlatformFinished

SchedulerEvent = KeywordResult | PlatformFinished


class PlatformScheduler:
    """Run platforms concurrently and keywords sequentially per platform."""

    def __init__(
        self,
        adapters: dict[str, PlatformAdapter],
        keywords: list[str],
        max_workers: int,
        max_browser_workers: int,
        queue_size: int,
    ) -> None:
        self.adapters = adapters
        self.keywords = keywords
        self.max_workers = max(1, min(max_workers, len(adapters) or 1))
        self.max_browser_workers = max(1, max_browser_workers)
        self.queue_size = max(1, queue_size)

    def events(self) -> Iterator[SchedulerEvent]:
        queue: Queue[SchedulerEvent] = Queue(maxsize=self.queue_size)
        browser_slots = BoundedSemaphore(self.max_browser_workers)

        def run_platform(adapter: PlatformAdapter) -> None:
            try:
                for keyword in self.keywords:
                    try:
                        if adapter.resource_group == "browser":
                            with browser_slots:
                                leads = adapter.scrape(keyword)
                        else:
                            leads = adapter.scrape(keyword)
                        queue.put(
                            KeywordResult(
                                platform_worker=adapter.name,
                                keyword=keyword,
                                leads=leads,
                            )
                        )
                    except Exception as exc:
                        queue.put(
                            KeywordResult(
                                platform_worker=adapter.name,
                                keyword=keyword,
                                error=str(exc),
                            )
                        )
            finally:
                queue.put(PlatformFinished(adapter.name))

        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="platform",
        ) as executor:
            futures = [
                executor.submit(run_platform, adapter)
                for adapter in self.adapters.values()
            ]
            finished = 0
            while finished < len(futures):
                event = queue.get()
                if isinstance(event, PlatformFinished):
                    finished += 1
                yield event

            for future in futures:
                future.result()
