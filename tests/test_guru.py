"""Regression tests for Guru job-detail URL extraction."""

import unittest
from datetime import datetime, timezone

from upwork_scraper.guru import GuruScraper
from upwork_scraper.models import JobLead


class GuruScraperTests(unittest.TestCase):
    def test_uses_title_detail_url_instead_of_category_url(self) -> None:
        html = """
        <article class="record jobRecord">
          <div class="jobRecord__meta">Posted 2 hrs ago · 3 Quotes Received</div>
          <h2 class="jobRecord__title">
            <a href="/jobs/front-end-developer/2119835&SearchUrl=search.aspx?">
              Front End Developer
            </a>
          </h2>
          <div class="jobRecord__budget">Fixed Price</div>
          <div class="jobRecord__body">Build a web application.</div>
          <p class="freelancerAvatar__subText">
            <strong>United States</strong>
          </p>
          <a href="/d/jobs/c/programming-development/">
            Programming &amp; Development
          </a>
        </article>
        """

        scraper = GuruScraper()
        try:
            leads = scraper._parse_records(html)
        finally:
            scraper._session.close()

        self.assertEqual(len(leads), 1)
        self.assertEqual(
            leads[0].url,
            "https://www.guru.com/jobs/front-end-developer/2119835",
        )
        self.assertEqual(leads[0].job_id, "2119835")
        self.assertEqual(leads[0].country, "United States")

    def test_converts_relative_posted_time_to_absolute_date(self) -> None:
        now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

        posted = GuruScraper._parse_posted_date(
            "Posted 2 hrs ago \u00b7 3 Quotes Received",
            now,
        )

        self.assertEqual(posted, "Jul 31, 2026")

    def test_preserves_absolute_posted_date_format(self) -> None:
        posted = GuruScraper._parse_posted_date(
            "Posted on Jul 17, 2026 \u00b7 26 Quotes Received"
        )

        self.assertEqual(posted, "Jul 17, 2026")

    def test_filters_returned_leads_to_us_and_canada(self) -> None:
        scraper = GuruScraper(["United States", "Canada"])
        try:
            leads = scraper._target_leads([
                JobLead(title="Toronto", country="Canada"),
                JobLead(title="London", country="United Kingdom"),
            ])
        finally:
            scraper.close()

        self.assertEqual([lead.title for lead in leads], ["Toronto"])


if __name__ == "__main__":
    unittest.main()
