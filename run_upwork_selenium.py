#!/usr/bin/env python3
"""Run Upwork Selenium scraper with all config keywords (except python)."""
import sys
sys.path.insert(0, "/Users/mac/Desktop/leadnew")

import logging
from upwork_scraper.config import ScraperConfig
from upwork_scraper.selenium_scraper import UpworkSeleniumScraper
from upwork_scraper.models import JobLead

logging.basicConfig(level=logging.INFO, format="%(message)s")

config = ScraperConfig()
keywords = [k for k in config.keywords if "python" not in k.lower()]
print(f"Keywords to scrape: {len(keywords)}")

scraper = UpworkSeleniumScraper(config)
all_leads: list[JobLead] = []
seen_urls: set[str] = set()

try:
    for i, kw in enumerate(keywords, 1):
        print(f"\n[{i}/{len(keywords)}] Searching: {kw}")
        try:
            leads = scraper.search_keyword(kw)
            new = 0
            for l in leads:
                l.keyword_searched = kw
                if l.url not in seen_urls:
                    seen_urls.add(l.url)
                    all_leads.append(l)
                    new += 1
            print(f"  Found {len(leads)} total, {new} new. (Total: {len(all_leads)})")
        except Exception as e:
            print(f"  [SKIP] Error: {e}")
            continue
finally:
    scraper.close()
    print(f"\n\n=== FINAL: {len(all_leads)} total leads ===")
