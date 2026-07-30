from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock

from upwork_scraper.config import ScraperConfig
from upwork_scraper.vollna import VollnaScraper


RSS = """\
<rss>
  <channel>
    <item>
      <title>Web Development Project (Fixed Price: 500 USD)</title>
      <description>Need web development help.</description>
      <link>https://example.com/web</link>
      <pubDate>Thu, 30 Jul 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Marketing Campaign Specialist</title>
      <description>Need a marketing campaign.</description>
      <link>https://example.com/marketing</link>
      <pubDate>Thu, 30 Jul 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


class VollnaBatchTests(unittest.TestCase):
    def test_fetches_feed_once_for_all_keywords(self) -> None:
        scraper = VollnaScraper(ScraperConfig(target_locations=[]))
        fetches = [0]

        def fetch(_: str) -> str:
            fetches[0] += 1
            return RSS

        scraper._fetch = fetch
        try:
            results = scraper.search_keywords(
                ["web development", "marketing"]
            )
        finally:
            scraper.close()

        self.assertEqual(fetches[0], 1)
        self.assertEqual(len(results["web development"]), 1)
        self.assertEqual(len(results["marketing"]), 1)

    def test_enriches_each_unique_upwork_job_once(self) -> None:
        scraper = VollnaScraper(ScraperConfig())
        resolver = Mock()
        scraper._location_resolver = resolver
        lead = scraper._extract_job(
            ET.fromstring(
                """
                <item>
                  <title>Qualified Upwork Project</title>
                  <description>Need React development.</description>
                  <link>https://www.upwork.com/jobs/~012345</link>
                </item>
                """
            ),
            "react",
        )

        scraper._enrich_locations([lead, lead])

        resolver.enrich_client_locations.assert_called_once_with(
            [lead]
        )

    def test_filters_resolved_leads_to_us_and_canada(self) -> None:
        scraper = VollnaScraper(ScraperConfig())
        try:
            us = scraper._extract_job(
                ET.fromstring(
                    """
                    <item>
                      <title>United States Project</title>
                      <description>Location: United States</description>
                    </item>
                    """
                ),
                "project",
            )
            uk = scraper._extract_job(
                ET.fromstring(
                    """
                    <item>
                      <title>United Kingdom Project</title>
                      <description>Location: United Kingdom</description>
                    </item>
                    """
                ),
                "project",
            )
            leads = scraper._target_leads([us, uk])
        finally:
            scraper.close()

        self.assertEqual([lead.title for lead in leads], [
            "United States Project"
        ])


if __name__ == "__main__":
    unittest.main()
