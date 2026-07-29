"""Guru.com job scraper."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from curl_cffi import requests as cffi_requests
from selectolax.parser import HTMLParser

from .models import JobLead

logger = logging.getLogger(__name__)

GURU_SKILLS: dict[str, str] = {
    "python": "python",
    "data-entry": "data-entry",
    "web-scraping": "web-scraping",
    "lead-generation": "lead-generation",
    "django": "python",
    "fastapi": "python",
    "flask": "python",
    "javascript": "javascript",
    "react": "react",
    "react.js": "react",
    "reactjs": "react",
}

BASE_URL = "https://www.guru.com"


class GuruScraper:
    def __init__(self) -> None:
        self._session = cffi_requests.Session(impersonate="chrome")

    def _pick_skill(self, keyword: str) -> str:
        kw = keyword.lower().strip()
        if kw in GURU_SKILLS:
            return GURU_SKILLS[kw]
        return re.sub(r"[^a-z0-9]+", "-", kw).strip("-")

    def _parse_records(self, html: str) -> list[JobLead]:
        tree = HTMLParser(html)
        leads: list[JobLead] = []

        for rec in tree.css(".record.jobRecord"):
            title_el = rec.css_first(".jobRecord__title")
            if not title_el:
                continue
            title = title_el.text(strip=True)

            budget_el = rec.css_first(".jobRecord__budget")
            budget = budget_el.text(strip=True) if budget_el else ""

            meta_el = rec.css_first(".jobRecord__meta")
            meta = meta_el.text(strip=True) if meta_el else ""

            body_el = rec.css_first(".jobRecord__body")
            description = body_el.text(strip=True)[:300] if body_el else ""

            skill_els = rec.css(".jobRecord__skills a, [class*=skill] a")
            skills = [s.text(strip=True) for s in skill_els if s.text(strip=True)]

            link_el = rec.css_first("a[href*='/d/jobs/']")
            href = link_el.attributes.get("href", "") if link_el else ""

            posted = ""
            quotes = ""
            if meta:
                m_posted = re.search(r"on\s+(.+?)(?:\u00b7|$)", meta)
                if m_posted:
                    posted = m_posted.group(1).strip()
                m_quotes = re.search(r"(\d+)\s*Quotes?\s*Received", meta)
                if m_quotes:
                    quotes = m_quotes.group(1)

            lead = JobLead(
                title=title,
                company_client="Guru Client",
                platform="Guru",
                location="",
                job_type="",
                budget=budget,
                posted_date=posted,
                url=urljoin(BASE_URL, href) if href else "",
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
        skill = self._pick_skill(keyword)
        url = f"{BASE_URL}/d/jobs/skill/{skill}/"
        logger.info("Guru: fetching %s", url)

        try:
            resp = self._session.get(
                url,
                timeout=30,
                headers={"Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
            )
            if resp.status_code != 200:
                logger.warning("Guru: status %d for %s", resp.status_code, url)
                return []
        except Exception as exc:
            logger.error("Guru: request failed: %s", exc)
            return []

        leads = self._parse_records(resp.text)
        logger.info("Guru: parsed %d jobs", len(leads))
        return leads[:max_results]
