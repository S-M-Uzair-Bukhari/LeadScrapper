"""Freelancer.com job scraper."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from curl_cffi import requests as cffi_requests
from selectolax.parser import HTMLParser

from .models import JobLead

logger = logging.getLogger(__name__)

FREELANCER_CATEGORIES: dict[str, str] = {
    "python": "/job-search/python/",
    "data-entry": "/job-search/data-entry/",
    "web-scraping": "/job-search/web-scraping/",
    "lead-generation": "/job-search/lead-generation/",
    "django": "/job-search/django/",
    "fastapi": "/job-search/fastapi/",
    "flask": "/job-search/python/",
    "javascript": "/job-search/javascript/",
    "react": "/job-search/react-js/",
    "react.js": "/job-search/react-js/",
    "reactjs": "/job-search/react-js/",
    "wordpress": "/job-search/wordpress/",
}

BASE_URL = "https://www.freelancer.com"


class FreelancerScraper:
    def __init__(self) -> None:
        self._session = cffi_requests.Session(impersonate="chrome")

    def _pick_category(self, keyword: str) -> str:
        kw = keyword.lower().strip()
        if kw in FREELANCER_CATEGORIES:
            return FREELANCER_CATEGORIES[kw]
        slug = re.sub(r"[^a-z0-9]+", "-", kw).strip("-")
        return f"/job-search/{slug}/"

    def _parse_cards(self, html: str, source_url: str) -> list[JobLead]:
        tree = HTMLParser(html)
        leads: list[JobLead] = []

        for card in tree.css(".JobSearchCard-item"):
            title_el = card.css_first("a.JobSearchCard-primary-heading-link")
            if not title_el:
                continue

            title = title_el.text(strip=True)
            href = title_el.attributes.get("href", "")
            job_url = urljoin(BASE_URL, href) if href else ""

            budget_el = card.css_first(
                ".JobSearchCard-primary-budget, [class*=budget]"
            )
            raw_budget = budget_el.text(strip=True) if budget_el else ""
            budget = re.sub(r"Average bid$", "", raw_budget).strip()

            desc_el = card.css_first(".JobSearchCard-primary-description")
            description = desc_el.text(strip=True)[:500] if desc_el else ""

            skills_els = card.css(
                ".JobSearchCard-primary-skills a, [class*=skill] a"
            )
            skills = [s.text(strip=True) for s in skills_els if s.text(strip=True)]

            days_el = card.css_first(".JobSearchCard-primary-heading-days")
            time_left = days_el.text(strip=True) if days_el else ""

            verified = bool(card.css_first("[class*=verified], [class*=Verified]"))

            lead = JobLead(
                title=title,
                company_client="Freelancer Client",
                platform="Freelancer",
                location="",
                job_type="",
                budget=budget,
                posted_date=time_left,
                url=job_url,
                description=description[:500],
                skills_required=", ".join(skills) if skills else "",
                experience_level="",
                country="",
                valid_job="Yes",
                job_id=href.split("/")[-1] if href else "",
            )
            leads.append(lead)

        return leads

    def scrape(self, keyword: str, max_results: int = 25) -> list[JobLead]:
        cat = self._pick_category(keyword)
        url = f"{BASE_URL}{cat}"
        logger.info("Freelancer: fetching %s", url)

        try:
            resp = self._session.get(
                url,
                timeout=30,
                headers={"Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
            )
            if resp.status_code != 200:
                logger.warning("Freelancer: status %d", resp.status_code)
                return []
        except Exception as exc:
            logger.error("Freelancer: request failed: %s", exc)
            return []

        leads = self._parse_cards(resp.text, url)
        logger.info("Freelancer: parsed %d jobs", len(leads))
        return leads[:max_results]
