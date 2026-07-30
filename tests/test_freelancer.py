"""Regression tests for Freelancer posting-date extraction."""

import unittest
from datetime import datetime, timezone

from upwork_scraper.freelancer import FreelancerScraper
from upwork_scraper.models import JobLead


class FreelancerScraperTests(unittest.TestCase):
    def test_search_card_deadline_is_not_saved_as_posted_date(self) -> None:
        html = """
        <div class="JobSearchCard-item">
          <a class="JobSearchCard-primary-heading-link"
             href="/projects/python/example-project">
            Example Project
          </a>
          <span class="JobSearchCard-primary-heading-days">6 days left</span>
          <p class="JobSearchCard-primary-description">Build something.</p>
        </div>
        """

        scraper = FreelancerScraper()
        try:
            leads = scraper._parse_cards(
                html, "https://www.freelancer.com/job-search/python/"
            )
        finally:
            scraper._session.close()

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].posted_date, "")

    def test_detail_page_provides_actual_posting_age(self) -> None:
        html = """
        <p>
          Posted
          <fl-relative-time>
            <span>about 3 hours ago</span>
          </fl-relative-time>
        </p>
        <p>Ends in 6 days</p>
        """

        self.assertEqual(
            FreelancerScraper._parse_posted_date(html),
            "about 3 hours ago",
        )

    def test_embedded_start_time_overrides_five_second_placeholder(
        self,
    ) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        posted_at = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)
        start_time_ms = int(posted_at.timestamp() * 1000)
        html = f"""
        <script>
          {{"project": {{"startTime": {start_time_ms}}}}}
        </script>
        <p>
          Posted
          <fl-relative-time><span>5 seconds ago</span></fl-relative-time>
        </p>
        """

        self.assertEqual(
            FreelancerScraper._parse_posted_date(html, now),
            "22 hours ago",
        )

    def test_embedded_project_data_provides_client_country(self) -> None:
        html = """
        <script>
          {"project": {
            "client": {
              "registrationTime": 123,
              "address": {
                "city": "Toronto",
                "country": "Canada",
                "countryCode": "ca"
              }
            }
          }}
        </script>
        """

        self.assertEqual(
            FreelancerScraper._parse_client_country(html),
            "Canada",
        )

    def test_filters_returned_leads_to_us_and_canada(self) -> None:
        scraper = FreelancerScraper(["United States", "Canada"])
        try:
            leads = scraper._target_leads([
                JobLead(title="US", country="United States"),
                JobLead(title="CA", country="Canada"),
                JobLead(title="India", country="India"),
                JobLead(title="Unknown"),
            ])
        finally:
            scraper.close()

        self.assertEqual(
            [lead.title for lead in leads],
            ["US", "CA"],
        )


if __name__ == "__main__":
    unittest.main()
