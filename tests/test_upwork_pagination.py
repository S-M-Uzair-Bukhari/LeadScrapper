from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from upwork_scraper.config import ScraperConfig
from upwork_scraper.models import JobLead
from upwork_scraper.selenium_scraper import UpworkSeleniumScraper


class UpworkPaginationTests(unittest.TestCase):
    def test_catch_up_requests_pages_until_lookback_boundary(self) -> None:
        config = ScraperConfig(
            max_results_per_keyword=1000,
            page_limit=100,
            collection_recency_hours=14,
        )
        scraper = UpworkSeleniumScraper(config)
        scraper._get_driver = lambda: object()
        scraper._ensure_logged_in = lambda _: True

        requested_pages: list[int] = []
        pages = {
            1: [
                JobLead(
                    title="Recent 1",
                    url="https://www.upwork.com/jobs/1",
                    posted_date="1 hour ago",
                )
            ],
            2: [
                JobLead(
                    title="Recent 2",
                    url="https://www.upwork.com/jobs/2",
                    posted_date="13 hours ago",
                )
            ],
            3: [
                JobLead(
                    title="Boundary",
                    url="https://www.upwork.com/jobs/3",
                    posted_date="15 hours ago",
                )
            ],
        }

        def load_jobs(_, url: str, max_scrolls: int):
            query = parse_qs(urlparse(url).query)
            page = int(query["page"][0])
            self.assertEqual(query["per_page"], ["50"])
            requested_pages.append(page)
            return pages.get(page, [])

        scraper._load_jobs = load_jobs
        scraper._parse_card = lambda card, _: card

        leads = scraper._scrape_keyword("web development")

        self.assertEqual(requested_pages, [1, 2, 3])
        self.assertEqual(len(leads), 3)

    def test_date_only_values_are_not_rejected_when_day_overlaps_window(
        self,
    ) -> None:
        from datetime import datetime, timezone

        from upwork_scraper.pipeline.recency_filter import RecencyFilter

        now = datetime(2026, 7, 30, 14, 30, tzinfo=timezone.utc)
        recency_filter = RecencyFilter(14)

        self.assertTrue(
            recency_filter.matches(
                JobLead(title="Same day", posted_date="Jul 30, 2026"),
                now,
            )
        )
        self.assertFalse(
            recency_filter.matches(
                JobLead(title="Previous day", posted_date="Jul 29, 2026"),
                now,
            )
        )

    def test_stops_when_upwork_repeats_the_same_page(self) -> None:
        config = ScraperConfig(
            max_results_per_keyword=1000,
            page_limit=100,
            collection_recency_hours=14,
        )
        scraper = UpworkSeleniumScraper(config)
        scraper._get_driver = lambda: object()
        scraper._ensure_logged_in = lambda _: True
        card = JobLead(
            title="Repeated",
            url="https://www.upwork.com/jobs/repeated",
            posted_date="1 hour ago",
        )
        calls = [0]

        def load_jobs(*_, **__):
            calls[0] += 1
            return [card]

        scraper._load_jobs = load_jobs
        scraper._parse_card = lambda value, _: value

        leads = scraper._scrape_keyword("web development")

        self.assertEqual(calls[0], 2)
        self.assertEqual(len(leads), 1)


if __name__ == "__main__":
    unittest.main()
