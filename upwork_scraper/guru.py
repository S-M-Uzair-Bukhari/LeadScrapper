"""Guru.com job scraper."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from curl_cffi import requests as cffi_requests
from selectolax.parser import HTMLParser

from .models import JobLead
from .pipeline.recency_filter import RecencyFilter

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

    def close(self) -> None:
        self._session.close()

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
            location_el = rec.css_first(
                ".freelancerAvatar__subText strong"
            )
            client_country = (
                location_el.text(strip=True) if location_el else ""
            )

            # Guru places the canonical job-detail link inside the title.
            # Other links in the record point to category pages under
            # ``/d/jobs/`` and must not be saved as the lead URL.
            link_el = title_el.css_first("a[href]")
            href = link_el.attributes.get("href", "") if link_el else ""
            clean_href = re.split(r"[?&]", href, maxsplit=1)[0]
            job_id_match = re.search(r"/(\d+)/?$", clean_href)

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
                location=client_country,
                job_type="",
                budget=budget,
                posted_date=posted,
                url=urljoin(BASE_URL, clean_href) if clean_href else "",
                description=description[:500],
                skills_required=", ".join(skills) if skills else "",
                experience_level="",
                country=client_country,
                valid_job="Yes",
                job_id=job_id_match.group(1) if job_id_match else "",
            )
            leads.append(lead)

        return leads

    def scrape(
        self,
        keyword: str,
        max_results: int = 25,
        page_limit: int = 1,
        recency_hours: float | None = None,
    ) -> list[JobLead]:
        skill = self._pick_skill(keyword)
        url = f"{BASE_URL}/d/jobs/skill/{skill}/"
        leads: list[JobLead] = []
        seen: set[str] = set()
        for page in range(1, max(1, page_limit) + 1):
            logger.info("Guru: fetching %s (page %d)", url, page)
            try:
                resp = self._session.get(
                    url,
                    params={"page": page},
                    timeout=30,
                    headers={
                        "Accept": "text/html",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Guru: status %d for %s", resp.status_code, url
                    )
                    break
            except Exception as exc:
                logger.error("Guru: request failed: %s", exc)
                break

            page_leads = self._parse_records(resp.text)
            for lead in page_leads:
                key = lead.url or lead.title
                if key not in seen:
                    seen.add(key)
                    leads.append(lead)
            if (
                len(leads) >= max_results
                or not page_leads
                or RecencyFilter.page_reaches_boundary(
                    page_leads,
                    recency_hours,
                )
            ):
                break

        logger.info("Guru: parsed %d jobs", len(leads))
        return leads[:max_results]
