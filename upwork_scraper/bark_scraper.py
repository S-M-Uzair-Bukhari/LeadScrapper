"""
Bark.com scraper using Selenium + undetected_chromedriver.
Logs in automatically with password (FusionAuth password panel),
then scrapes buyer requests from the professional dashboard.
"""

import re
import time
import logging
import os
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from .browser_cleanup import close_chrome_safely
from .config import ScraperConfig
from .models import JobLead

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.bark.com/en/gb/login/"
DASHBOARD_URL = "https://www.bark.com/sellers/home/"
LEADS_URL = "https://www.bark.com/sellers/leads/"

RESULT_CARD_SELECTORS = [
    ".leads-list-item-card",
    "[data-testid*='request']",
    "[data-testid*='buyer']",
    "[data-testid*='lead-card']",
    "[data-testid*='opportunity']",
    "[data-testid*='card']",
    "[class*='buyer-request']",
    "[class*='request-card']",
    "[class*='lead-card']",
    "[class*='opportunity-card']",
    "[class*='job-card']",
    "article[class*='request']",
    "article[class*='card']",
]

TITLE_SELECTORS = [
    "a[href*='/request/']",
    "a[href*='/buyer-request/']",
    "h2 a",
    "h3 a",
    "h4 a",
    "h2",
    "h3",
    "h4",
    "[class*='title'] a",
    "[class*='title']",
    "[class*='heading'] a",
    "[class*='heading']",
]


class BarkScraper:
    """Scrape Bark.com buyer requests from the professional dashboard.
    Uses credentials from .env to log in via FusionAuth password panel."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self._driver: Optional[uc.Chrome] = None
        self._seen_ids: set[str] = set()
        self._logged_in = False
        self._cached_all_leads: Optional[list[JobLead]] = None
        self._cached_raw: Optional[list[dict]] = None

    # ==================================================================
    # Public API
    # ==================================================================

    def search_keyword(self, keyword: str) -> list[JobLead]:
        if self._cached_raw is None:
            self._cached_raw = self._scrape_all_cards()
        leads = self._filter_and_tag(self._cached_raw, keyword)
        return leads[:self.config.max_results_per_keyword]

    def _scrape_all_cards(self) -> list[dict]:
        driver = self._get_driver()
        if not self._ensure_logged_in(driver):
            logger.error("Cannot scrape — login failed.")
            return []

        driver.get("https://www.bark.com/sellers/dashboard/")
        time.sleep(12)
        driver.execute_script("window.stop();")
        time.sleep(3)

        self._search_on_dashboard(driver, "")
        try:
            self._scroll_to_load(
                driver, max_scrolls=self.config.page_limit
            )
        except WebDriverException:
            logger.warning("Scroll failed.")

        cards = self._find_cards(driver)
        logger.info("Found %d total cards on dashboard.", len(cards))

        raw = []
        for card in cards:
            try:
                data = self._extract_card_data(card)
                if data and data.get("title"):
                    raw.append(data)
            except WebDriverException:
                continue

        logger.info("Extracted %d leads from dashboard.", len(raw))
        return raw

    def _filter_and_tag(self, raw: list[dict], keyword: str) -> list[JobLead]:
        leads = []
        for data in raw:
            location = data.get("location", "")
            title = data["title"]
            if location:
                title = f"{title} - {location}"
            dedup_key = f"{title}|{location}|{data.get('posted_date','')}"
            if dedup_key in self._seen_ids:
                continue
            self._seen_ids.add(dedup_key)
            leads.append(JobLead(
                title=title,
                url=data.get("url", ""),
                description=(data.get("description") or "")[:1000],
                budget=data.get("budget", ""),
                posted_date=data.get("posted_date", ""),
                platform="Bark.com",
                keyword_searched=keyword,
                location=location,
            ))
        return leads

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
                close_chrome_safely(self._driver)
                self._driver = None
        logger.info("Launching Chrome via undetected_chromedriver...")
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        if os.getenv("RUNNING_IN_CONTAINER") == "1":
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        version = os.getenv("CHROME_VERSION_MAIN")
        driver_path = os.getenv("CHROMEDRIVER_PATH")
        browser_path = os.getenv("CHROME_BINARY")
        launch_options: dict[str, object] = {"options": options}
        if version:
            launch_options["version_main"] = int(version)
        if driver_path:
            launch_options["driver_executable_path"] = driver_path
        if browser_path:
            launch_options["browser_executable_path"] = browser_path
        self._driver = uc.Chrome(**launch_options)
        self._driver.set_page_load_timeout(120)
        return self._driver

    def _ensure_logged_in(self, driver: uc.Chrome) -> bool:
        if self._logged_in:
            return True

        username = self.config.bark_username
        password = self.config.bark_password
        if not username or not password:
            logger.error("BARK_USERNAME or BARK_PASSWORD not set in .env")
            return False

        logger.info("Navigating to dashboard to check login status...")
        self._safe_navigate(driver, DASHBOARD_URL, 10)

        if "login" not in driver.current_url.lower():
            logger.info("Already logged in.")
            self._logged_in = True
            return True

        logger.info("Login page detected. Logging in via password panel...")
        self._login_with_password(driver, username, password)

        pause = 120
        logger.info(f"Waiting up to {pause}s for login to complete...")
        end = time.time() + pause
        while time.time() < end:
            try:
                current = driver.current_url.lower()
                if "login" not in current and "oauth2" not in current and len(current) > 15:
                    logger.info("Login successful. URL: %s", current)
                    time.sleep(3)
                    self._safe_navigate(driver, DASHBOARD_URL, 10)
                    if "login" not in driver.current_url.lower():
                        self._logged_in = True
                        return True
            except Exception:
                pass
            time.sleep(2)

        logger.warning("Login not confirmed within timeout.")
        return False

    @staticmethod
    def _safe_navigate(driver, url: str, fallback_wait: int = 10):
        try:
            driver.get(url)
        except Exception:
            logger.debug("Page load timeout during navigate to %s, continuing...", url)
            time.sleep(fallback_wait)
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

    def _login_with_password(self, driver: uc.Chrome, username: str, password: str):
        try:
            show_pw_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#show-password"))
            )
            driver.execute_script("arguments[0].click();", show_pw_btn)
            logger.info("Clicked 'Use password instead' button.")
        except TimeoutException:
            logger.warning("Could not find 'Use password instead' button; trying password form directly.")

        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#pw-loginId"))
            )
            email_input.clear()
            email_input.send_keys(username)
            logger.info("Entered email.")
        except TimeoutException:
            logger.warning("Could not find #pw-loginId, trying input[name='loginId']")
            try:
                email_input = driver.find_element(By.CSS_SELECTOR, "input[name='loginId']")
                email_input.clear()
                email_input.send_keys(username)
            except Exception:
                logger.error("Could not find email input at all.")
                return

        try:
            pw_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#pw-password"))
            )
            pw_input.clear()
            pw_input.send_keys(password)
            logger.info("Entered password.")
        except TimeoutException:
            logger.warning("Could not find #pw-password, trying input[name='password']")
            try:
                pw_input = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
                pw_input.clear()
                pw_input.send_keys(password)
            except Exception:
                logger.error("Could not find password input.")
                return

        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, "#panel-password button[type='submit']")
            submit_btn.click()
            logger.info("Clicked login submit button.")
        except Exception:
            try:
                pw_input.send_keys(Keys.ENTER)
                logger.info("Pressed Enter to submit login.")
            except Exception:
                logger.error("Could not submit login form.")

    # ==================================================================
    # Scraping
    # ==================================================================

    def _scrape_keyword(self, keyword: str) -> list[JobLead]:
        driver = self._get_driver()

        if not self._ensure_logged_in(driver):
            logger.error("Cannot scrape — login failed.")
            return []

        leads = self._search_and_scrape(driver, keyword)
        logger.info("Found %d leads for '%s'", len(leads), keyword)
        return leads

    def _search_and_scrape(self, driver: uc.Chrome, keyword: str) -> list[JobLead]:
        # Navigate directly to dashboard/leads page
        try:
            logger.info("Navigating directly to leads page...")
            driver.get("https://www.bark.com/sellers/dashboard/")
            time.sleep(12)
            driver.execute_script("window.stop();")
        except Exception as exc:
            logger.warning("Navigation to dashboard had issue: %s", exc)
            time.sleep(5)

        time.sleep(3)

        search_found = self._search_on_dashboard(driver, keyword)
        if search_found:
            time.sleep(4)

        try:
            self._scroll_to_load(
                driver, max_scrolls=self.config.page_limit
            )
        except WebDriverException as exc:
            logger.warning("Scroll failed (session may have died): %s", exc)
            return []

        cards = self._find_cards(driver)

        if not cards:
            logger.warning("No cards found on dashboard for '%s'.", keyword)
            logger.info("Current URL: %s", driver.current_url)
            return []

        logger.info("Found %d potential card(s).", len(cards))

        leads = []
        for card in cards:
            try:
                job = self._parse_card(card, keyword)
                if not job or not job.title:
                    continue
                dedup_key = job.url or f"{job.title}|{job.location}|{job.posted_date}"
                if dedup_key not in self._seen_ids:
                    self._seen_ids.add(dedup_key)
                    leads.append(job)
            except WebDriverException:
                continue

        if not leads:
            logger.warning("No valid leads parsed from %d cards.", len(cards))
            return []
            logger.info("Dumping page element structure for selector debugging...")
            structure = driver.execute_script("""
                var results = [];
                var all = document.querySelectorAll('*');
                all.forEach(function(el, i) {
                    if (i > 500) return;
                    var rect = el.getBoundingClientRect();
                    var text = (el.textContent || '').trim();
                    if (rect.width > 200 && rect.height > 50 && text.length > 20) {
                        var tag = el.tagName.toLowerCase();
                        var cls = (el.className || '').toString().substring(0, 100);
                        var testid = el.getAttribute('data-testid') || '';
                        if (testid || cls.includes('lead') || cls.includes('card') || cls.includes('request') || tag === 'article' || tag === 'li') {
                            results.push({
                                tag: tag,
                                class: cls.substring(0, 80),
                                testid: testid,
                                text: text.substring(0, 60),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                });
                return JSON.stringify(results, null, 2);
            """)
            logger.info("Page card-like elements:\n%s", structure)

        return leads

    def _click_leads_link(self, driver: uc.Chrome) -> bool:
        leads_url = "https://www.bark.com/sellers/dashboard/"
        logger.info("Navigating to Leads page: %s", leads_url)
        try:
            driver.execute_script(f"window.location.href = '{leads_url}';")
        except Exception:
            try:
                driver.get(leads_url)
            except Exception:
                pass
        time.sleep(8)
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        if "login" not in driver.current_url.lower():
            return True
        return False

    def _search_on_dashboard(self, driver: uc.Chrome, keyword: str) -> bool:
        search_selectors = [
            "input[type='search']",
            "input[placeholder*='Search']",
            "input[placeholder*='search']",
            "input[placeholder*='Find']",
            "input[placeholder*='find']",
            "input[name='search']",
            "input[name='q']",
            "input[name='query']",
            "input[class*='search']",
            "#search",
            "[data-testid*='search'] input",
            "[data-testid*='Search'] input",
        ]

        for selector in search_selectors:
            try:
                search_input = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                search_input.clear()
                search_input.send_keys(keyword)
                time.sleep(1)
                search_input.send_keys(Keys.ENTER)
                logger.info("Searched dashboard for '%s' using selector: %s", keyword, selector)
                return True
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug("Search selector '%s' failed: %s", selector, e)
                continue

        logger.info("No search input found on dashboard. Scraping all visible cards.")
        return False

    def _scroll_to_load(self, driver: uc.Chrome, max_scrolls: int = 30):
        for i in range(max_scrolls):
            prev_count = len(self._find_cards(driver))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_count = len(self._find_cards(driver))
            if new_count == prev_count:
                break
            logger.debug("Scroll %d: cards increased from %d to %d", i+1, prev_count, new_count)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

    def _find_cards(self, driver):
        for selector in RESULT_CARD_SELECTORS:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    return cards
            except Exception:
                continue
        return []

    # ==================================================================
    # Card Parsing
    # ==================================================================

    SKIP_TITLES = {"edit", "delete", "settings", "profile", "home", "dashboard",
                   "logout", "sign out", "my services", "my profile", "account",
                   "inbox", "messages", "notifications", "help", "support",
                   "pricing", "join as a professional", "log in", "sign in",
                   "back", "cancel", "save", "update", "view", "see all", ""}

    def _parse_card(self, card, keyword: str) -> Optional[JobLead]:
        data = self._extract_card_data(card)
        if not data or not data.get("title"):
            return None

        location = data.get("location", "")
        title = data["title"]
        if location:
            title = f"{title} - {location}"

        return JobLead(
            title=title,
            url=data.get("url", ""),
            description=(data.get("description") or "")[:1000],
            budget=data.get("budget", ""),
            posted_date=data.get("posted_date", ""),
            platform="Bark.com",
            keyword_searched=keyword,
            location=location,
        )

    def _extract_card_data(self, card):
        data = card.parent.execute_script("""
            var c = arguments[0];
            var result = {title: '', description: '', budget: '', posted_date: '', location: '', url: '', buyer_name: ''};

            // Title: first span inside bg-gray-100 div (service category)
            var bgDiv = c.querySelector('div.tw-bg-gray-100');
            if (bgDiv) {
                var spans = bgDiv.querySelectorAll('span');
                if (spans.length > 0) result.title = (spans[0].textContent || '').trim();
                if (spans.length > 1) result.description = (spans[1].textContent || '').trim();
            }

            // Location: first p with tw-font-gordita-regular tw-text-xs (city, postcode)
            var locP = c.querySelector('p.tw-font-gordita-regular.tw-text-xs');
            if (locP) result.location = (locP.textContent || '').trim();

            // Buyer name
            var nameEl = c.querySelector('[class*="tw-text-left"] p.tw-font-gordita-regular');
            if (!nameEl) nameEl = c.querySelector('p.tw-m-0');
            if (nameEl) result.buyer_name = (nameEl.textContent || '').trim();

            // Date: look for p or span elements with time phrases (including abbreviations "h", "m", "d")
            var dateEls = c.querySelectorAll('p, span');
            for (var i = 0; i < dateEls.length; i++) {
                var t = (dateEls[i].textContent || '').trim();
                if (/\\d+\\s*(min|hour|hr|h|day|d|week|w|month|sec|s)\\s*ago/i.test(t) || /just now/i.test(t)) {
                    result.posted_date = t;
                    break;
                }
            }

            // Budget: find leaf span directly containing "Credits" or "Credit"
            var allEls = c.querySelectorAll('span');
            for (var i = 0; i < allEls.length; i++) {
                var t = (allEls[i].textContent || '').trim();
                // Only match if this span's direct text (excluding children) matches
                var directText = '';
                for (var j = 0; j < allEls[i].childNodes.length; j++) {
                    if (allEls[i].childNodes[j].nodeType === 3) {
                        directText += allEls[i].childNodes[j].textContent;
                    }
                }
                directText = directText.trim();
                if (/^\\d+\\s*credit/i.test(directText)) {
                    result.budget = t;
                    break;
                }
            }

            // Fallback: look for any element with £ $ €
            if (!result.budget) {
                var walker = document.createTreeWalker(c, 4, null, false);
                while (walker.nextNode()) {
                    var t = (walker.currentNode.textContent || '').trim();
                    if (/[\\u00a3\\$\\u20ac]/.test(t)) {
                        result.budget = t;
                        break;
                    }
                }
            }

            return result;
        """, card)
        return data

    def _extract_link(self, card):
        for selector in TITLE_SELECTORS:
            els = card.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                tag = el.tag_name
                if tag == "a":
                    href = el.get_attribute("href")
                    text = el.text.strip()
                    if text and href and "javascript" not in href:
                        return text, href
                else:
                    text = el.text.strip()
                    if text:
                        links = el.find_elements(By.TAG_NAME, "a")
                        for link in links:
                            href = link.get_attribute("href")
                            if href and "javascript" not in href:
                                return text, href
                        return text, ""

        for link in card.find_elements(By.CSS_SELECTOR, "a[href*='/request/']"):
            href = link.get_attribute("href")
            text = link.text.strip()
            if text and href:
                return text, href

        for link in card.find_elements(By.TAG_NAME, "a"):
            href = link.get_attribute("href")
            text = link.text.strip()
            if text and href and "javascript" not in href and "login" not in href.lower():
                return text, href

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
    def _extract_budget(text: str) -> str:
        for line in (l.strip() for l in text.splitlines()):
            if not line:
                continue
            if any(sym in line for sym in ("\u00a3", "$", "\u20ac")) or "budget" in line.lower():
                return line
        return ""

    @staticmethod
    def _extract_location(text: str) -> str:
        for line in (l.strip() for l in text.splitlines()):
            if not line:
                continue
            low = line.lower()
            if any(k in low for k in ("near", "location", "postcode", "zip", "area")):
                return line
            if 2 <= len(line.split()) <= 4 and any(ch.isalpha() for ch in line):
                if not any(k in low for k in ("budget", "urgent", "view", "request", "responses")):
                    return line
        return ""

    @staticmethod
    def _extract_date(text: str) -> str:
        for line in (l.strip() for l in text.splitlines()):
            if not line:
                continue
            low = line.lower()
            if any(k in low for k in ("minute", "hour", "day", "week", "month", "just now",
                                      "ago", "today", "yesterday")):
                return line
        return ""
