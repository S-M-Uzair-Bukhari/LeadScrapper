"""Regression tests for Guru job-detail URL extraction."""

import unittest

from upwork_scraper.guru import GuruScraper


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


if __name__ == "__main__":
    unittest.main()
