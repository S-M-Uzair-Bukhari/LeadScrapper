from __future__ import annotations

import unittest

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
        scraper = VollnaScraper(ScraperConfig())
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


if __name__ == "__main__":
    unittest.main()
