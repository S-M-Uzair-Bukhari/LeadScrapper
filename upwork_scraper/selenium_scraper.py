"""
Upwork scraper using Selenium + undetected_chromedriver.
Logs in with user credentials and scrapes job listings directly
from Upwork's search results. Returns JobLead objects.
"""

import re
import time
import json
import logging
from urllib.parse import urlencode
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import ScraperConfig
from .browser_cleanup import close_chrome_safely, discard_chrome_safely
from .models import JobLead
from .pipeline.recency_filter import RecencyFilter

logger = logging.getLogger(__name__)
_DRIVER_LAUNCH_LOCK = Lock()

LOGIN_URL = "https://www.upwork.com/ab/account-security/login"
SEARCH_URL = "https://www.upwork.com/nx/search/jobs/"

JOB_CARD_SELECTORS = [
    "article[data-test='JobTile']",
    "section[data-test='JobTile']",
    "[data-test='job-tile-list'] article",
    "[data-test='job-tile-list'] section",
]
JOB_LINK_SELECTORS = [
    "a[data-test='job-tile-title-link']",
    "h2 a[href*='/jobs/']",
    "a[href*='/jobs/']",
]


class UpworkSeleniumScraper:
    """Scrape Upwork job data using Selenium with undetected_chromedriver.
    Requires a logged-in Upwork session (credentials in .env)."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self._driver: Optional[uc.Chrome] = None
        self._seen_ids: set[str] = set()
        self._cached_leads: Optional[list[JobLead]] = None

    # ==================================================================
    # Public API
    # ==================================================================

    def search_keyword(self, keyword: str) -> list[JobLead]:
        for attempt in range(2):
            try:
                leads = self._scrape_keyword(keyword)
                return leads[:self.config.max_results_per_keyword]
            except Exception as exc:
                if attempt == 0 and self._is_browser_failure(exc):
                    logger.warning(
                        "Upwork browser failed for '%s'; restarting its "
                        "isolated browser and retrying once: %s",
                        keyword,
                        exc,
                    )
                    self._discard_driver()
                    continue
                raise
        return []

    def close(self):
        if self._driver:
            close_chrome_safely(self._driver)
            self._driver = None
            logger.info("Browser closed.")

    # ==================================================================
    # Selenium Lifecycle
    # ==================================================================

    def _get_driver(self) -> uc.Chrome:
        if self._driver is not None:
            try:
                self._driver.current_url
                return self._driver
            except Exception:
                logger.info("Browser session lost, recreating...")
                self._discard_driver()
        logger.info("Launching Chrome via undetected_chromedriver...")
        with _DRIVER_LAUNCH_LOCK:
            options = uc.ChromeOptions()
            options.add_argument(
                "--disable-blink-features=AutomationControlled"
            )
            options.add_argument("--start-maximized")
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                ChromeDriverManager().install()
            except Exception:
                pass
            self._driver = uc.Chrome(version_main=150, options=options)
        self._driver.set_page_load_timeout(120)
        client_config = getattr(
            self._driver.command_executor,
            "_client_config",
            None,
        )
        if client_config is not None:
            client_config.timeout = self.config.selenium_command_timeout
        return self._driver

    def _discard_driver(self) -> None:
        driver = self._driver
        self._driver = None
        discard_chrome_safely(driver)

    @staticmethod
    def _is_browser_failure(exc: Exception) -> bool:
        if isinstance(exc, WebDriverException):
            return True
        message = str(exc).casefold()
        return (
            "localhost" in message
            and (
                "timed out" in message
                or "connection" in message
                or "max retries" in message
            )
        )

    def _ensure_logged_in(self, driver: uc.Chrome) -> bool:
        username = self.config.upwork_username
        password = self.config.upwork_password
        if not username or not password:
            logger.error("UPWORK_USERNAME or UPWORK_PASSWORD not set in .env")
            return False

        search_url = SEARCH_URL + "?" + urlencode({"sort": "recency", "q": "python"})
        driver.get(search_url)
        time.sleep(3)

        if "upwork.com/nx/" in driver.current_url:
            logger.info("Already logged in.")
            return True

        logger.info("Opening Upwork login page...")
        driver.get(LOGIN_URL)
        time.sleep(3)

        self._input_if_present(driver, [
            "input[name='login[username]']",
            "input#login_username",
            "input[type='email']",
        ], username, submit=True)
        time.sleep(2)

        self._input_if_present(driver, [
            "input[name='login[password]']",
            "input#login_password",
            "input[type='password']",
        ], password, submit=True)

        pause = 90  # seconds for 2FA / manual verification
        logger.info(f"Waiting up to {pause}s for login/2FA...")
        end = time.time() + pause
        while time.time() < end:
            if "upwork.com/nx/" in driver.current_url:
                logger.info("Login successful.")
                return True
            time.sleep(2)

        logger.warning("Login not confirmed within timeout.")
        return False

    @staticmethod
    def _input_if_present(driver, selectors, value, timeout=8, submit=True):
        if not value:
            return False
        for selector in selectors:
            try:
                el = WebDriverWait(driver, timeout).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                el.clear()
                el.send_keys(value)
                if submit:
                    el.send_keys(Keys.ENTER)
                return True
            except TimeoutException:
                continue
        return False

    # ==================================================================
    # Scraping
    # ==================================================================

    def _scrape_keyword(self, keyword: str) -> list[JobLead]:
        driver = self._get_driver()

        if not self._ensure_logged_in(driver):
            logger.error("Cannot scrape — login failed.")
            return []

        leads: list[JobLead] = []
        reference = datetime.now(timezone.utc)
        previous_page_signature: tuple[str, ...] | None = None
        for page in range(1, max(1, self.config.page_limit) + 1):
            feed_url = SEARCH_URL + "?" + urlencode({
                "sort": "recency",
                "q": keyword,
                "page": page,
                "per_page": min(50, self.config.max_results_per_keyword),
            })
            logger.info("Searching Upwork page %d: %s", page, feed_url)
            cards = self._load_jobs(
                driver,
                feed_url,
                max_scrolls=self.config.selenium_max_scrolls,
            )
            logger.info(
                "Loaded %d job cards from page %d for '%s'",
                len(cards),
                page,
                keyword,
            )
            if not cards:
                break

            parsed_page: list[JobLead] = []
            for card in cards:
                try:
                    job = self._parse_card(card, keyword)
                    if job:
                        parsed_page.append(job)
                except WebDriverException:
                    continue

            page_signature = tuple(job.url or job.title for job in parsed_page)
            if page_signature and page_signature == previous_page_signature:
                logger.warning(
                    "Upwork page %d repeated the previous page for '%s'; "
                    "stopping pagination.",
                    page,
                    keyword,
                )
                break
            previous_page_signature = page_signature

            for job in parsed_page:
                if job.url not in self._seen_ids:
                    self._seen_ids.add(job.url)
                    leads.append(job)
            if len(leads) >= self.config.max_results_per_keyword:
                break
            if self._reached_lookback_boundary(parsed_page, reference):
                logger.info(
                    "Reached the %.0f-hour lookback boundary on Upwork "
                    "page %d for '%s'.",
                    self.config.collection_recency_hours,
                    page,
                    keyword,
                )
                break

        return leads[:self.config.max_results_per_keyword]

    def _reached_lookback_boundary(
        self,
        leads: list[JobLead],
        reference: datetime,
    ) -> bool:
        hours = self.config.collection_recency_hours
        if hours is None:
            return False
        return RecencyFilter.page_reaches_boundary(
            leads,
            hours,
            reference,
        )

    def _load_jobs(self, driver, feed_url: str, max_scrolls: int = 8):
        driver.get(feed_url)
        try:
            selectors = ", ".join(JOB_CARD_SELECTORS)
            WebDriverWait(driver, 30).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selectors))
            )
        except TimeoutException:
            logger.warning("Timeout waiting for job cards.")
            return []

        seen = 0
        for _ in range(max_scrolls):
            cards = self._find_cards(driver)
            if len(cards) >= self.config.max_results_per_keyword:
                break
            if len(cards) == seen:
                break
            seen = len(cards)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        return self._find_cards(driver)

    def _find_cards(self, driver):
        cards = []
        seen = set()
        for selector in JOB_CARD_SELECTORS:
            for card in driver.find_elements(By.CSS_SELECTOR, selector):
                cid = card.id
                if cid not in seen:
                    seen.add(cid)
                    cards.append(card)
        return cards

    # ==================================================================
    # Card Parsing
    # ==================================================================

    def _parse_card(self, card, keyword: str) -> Optional[JobLead]:
        title, url = self._first_link(card)
        if not title or not url:
            return None

        raw_text = card.text
        desc = self._first_text(card, [
            "[data-test='UpCLineClamp JobDescription']",
            "[data-test='job-description-text']",
            "p",
        ])
        posted = self._extract_posted_str(card)
        skills = self._extract_skills(card)
        budget, job_type, exp_level = self._extract_job_meta(raw_text)
        client_location = self._first_text(card, [
            "[data-test='client-country']",
            "[data-test='client-location']",
            "[data-test='location']",
            "[data-qa='client-location']",
        ])

        return JobLead(
            title=title,
            url=url,
            description=desc[:1000],
            budget=budget,
            skills_required=", ".join(skills[:6]) if skills else "",
            posted_date=posted,
            job_type=job_type,
            experience_level=exp_level,
            platform="Upwork",
            keyword_searched=keyword,
            location=client_location,
            country=client_location,
        )

    def _first_link(self, card):
        for selector in JOB_LINK_SELECTORS:
            links = card.find_elements(By.CSS_SELECTOR, selector)
            for link in links:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href and "/jobs/" in href:
                    clean_url = href.split("?")[0]
                    return text, clean_url
        return "", ""

    @staticmethod
    def _first_text(card, selectors):
        for selector in selectors:
            els = card.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                text = el.text.strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _extract_skills(card):
        skills = []
        for selector in [
            "[data-test='TokenClamp JobAttrs'] button",
            "[data-test='skills-list'] a",
            "a[href*='ontology_skill_uid']",
        ]:
            for el in card.find_elements(By.CSS_SELECTOR, selector):
                text = el.text.strip()
                if text and text not in skills:
                    skills.append(text)
        return skills

    @staticmethod
    def _extract_posted_str(card):
        text = card.text
        patterns = [
            r"Posted\s+([^\n]+)",
            r"(\d+\s+(?:minute|hour|day|week)s?\s+ago)",
            r"(just now)",
            r"(yesterday)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_job_meta(text: str):
        budget = ""
        job_type = ""
        exp_level = ""

        m = re.search(r"(Hourly|Fixed-price)[:\s]*\$?([\d,]+(?:\.\d{2})?(?:\s*-\s*\$?[\d,]+(?:\.\d{2})?)?)", text, re.IGNORECASE)
        if m:
            job_type = m.group(1)
            budget = m.group(0).strip()
        else:
            m2 = re.search(r"(Hourly|Fixed-price)", text, re.IGNORECASE)
            if m2:
                job_type = m2.group(1)

        for level in ["Expert", "Intermediate", "Entry"]:
            if level.lower() in text.lower():
                exp_level = level
                break

        return budget, job_type, exp_level
