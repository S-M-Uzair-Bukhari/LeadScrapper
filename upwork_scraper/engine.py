"""
Lead generation engine — orchestrates multi-platform scraping,
deduplication, analysis, CSV export, and Google Sheets upload.
Each platform gets its own sheet/tab with color-coded priority.
"""

import csv
import json
import re
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from rich.console import Console
from rich.table import Table

from .config import ScraperConfig
from .models import JobLead
from .analyzer import LeadAnalyzer, LeadAnalysis
from .scraper import UpworkScraper
from .selenium_scraper import UpworkSeleniumScraper
from .bark_scraper import BarkScraper
from .vollna import VollnaScraper
from .freelancer import FreelancerScraper
from .guru import GuruScraper

logger = logging.getLogger(__name__)
console = Console()

PLATFORM_SHEET_MAP = {
    "Upwork": "Upwork",
    "Upwork (Vollna)": "Vollna",
    "Freelancer": "Freelancer",
    "Guru": "Guru",
    "Upwork (Selenium)": "Upwork",
    "Bark.com": "Bark.com",
}

SHEET_HEADERS = [
    "Job Title",
    "Job URL",
    "Job Platform",
    "Date Posted",
    "Priority",
    "Lead Score",
    "Company Name",
    "Company Website",
    "Company Domain",
    "Email",
    "Business Email",
    "Phone",
    "LinkedIn URL",
    "Decision-Maker Name",
    "Decision-Maker Title",
    "Budget",
    "Timeline",
    "Location",
    "Industry",
    "Technologies",
    "Services Required",
    "Qualification Reason",
    "Full Job Description",
]

# Google Sheets row colors (RGB)
COLOR_GREEN = {"red": 0.85, "green": 0.92, "blue": 0.83}
COLOR_YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.8}
COLOR_RED = {"red": 1.0, "green": 0.85, "blue": 0.85}
COLOR_HEADER = {"red": 0.2, "green": 0.2, "blue": 0.2}


class LeadEngine:
    """High-level engine that ties scraping, analysis, and output together."""

    def __init__(self, config: ScraperConfig | None = None):
        self.config = config or ScraperConfig()
        self.all_leads: list[JobLead] = []
        self.all_analyses: dict[str, LeadAnalysis] = {}
        self._seen_titles: set[str] = set()

        self._wayback = UpworkScraper(self.config)
        self._selenium = UpworkSeleniumScraper(self.config)
        self._vollna = VollnaScraper(self.config)
        self._freelancer = FreelancerScraper()
        self._guru = GuruScraper()
        self._bark = BarkScraper(self.config)
        self._analyzer = LeadAnalyzer()

    def run(self) -> list[JobLead]:
        """Run the full pipeline across all configured keywords."""
        platforms = self.config.resolved_platforms
        console.rule("[bold green]Multi-Platform Lead Generator")
        console.print(f"Platforms: [cyan]{', '.join(platforms)}[/cyan]")
        console.print(f"Keywords: [cyan]{len(self.config.keywords)} keywords configured[/cyan]")
        console.print(f"Max results/keyword: [cyan]{self.config.max_results_per_keyword}[/cyan]")
        console.print(f"Target locations: [cyan]{', '.join(self.config.target_locations)}[/cyan]")

        for kw in self.config.keywords:
            console.rule(f"[yellow]Searching: {kw}")

            if "upwork" in platforms:
                console.print("  [dim]Platform: Upwork (Wayback Machine)[/dim]")
                leads = self._wayback.search_keyword(kw)
                for l in leads:
                    l.keyword_searched = kw
                new = self._deduplicate(leads)
                self.all_leads.extend(new)
                console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")

            if "upwork_selenium" in platforms:
                console.print("  [dim]Platform: Upwork (Selenium - authenticated)[/dim]")
                try:
                    leads = self._selenium.search_keyword(kw)
                    for l in leads:
                        l.keyword_searched = kw
                    new = self._deduplicate(leads)
                    self.all_leads.extend(new)
                    console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")
                except Exception as exc:
                    logger.warning("Selenium scraper failed for '%s': %s", kw, exc)
                    console.print(f"  [red]Skipped (error: {exc})[/red]")

            if "vollna" in platforms:
                console.print("  [dim]Platform: Vollna (RSS Feed)[/dim]")
                leads = self._vollna.search_keyword(kw)
                for l in leads:
                    l.keyword_searched = kw
                new = self._deduplicate(leads)
                self.all_leads.extend(new)
                console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")

            if "freelancer" in platforms:
                console.print("  [dim]Platform: Freelancer.com[/dim]")
                leads = self._freelancer.scrape(kw, self.config.max_results_per_keyword)
                for l in leads:
                    l.keyword_searched = kw
                new = self._deduplicate(leads)
                self.all_leads.extend(new)
                console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")

            if "guru" in platforms:
                console.print("  [dim]Platform: Guru.com[/dim]")
                leads = self._guru.scrape(kw, self.config.max_results_per_keyword)
                for l in leads:
                    l.keyword_searched = kw
                new = self._deduplicate(leads)
                self.all_leads.extend(new)
                console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")

            if "bark" in platforms:
                console.print("  [dim]Platform: Bark.com[/dim]")
                try:
                    leads = self._bark.search_keyword(kw)
                    for l in leads:
                        l.keyword_searched = kw
                    new = self._deduplicate(leads)
                    self.all_leads.extend(new)
                    console.print(f"  Found {len(leads)} total, [green]{len(new)}[/green] new.")
                except Exception as exc:
                    logger.warning("Bark scraper failed for '%s': %s", kw, exc)
                    console.print(f"  [red]Skipped (error: {exc})[/red]")

        # Analyze all leads
        console.rule("[bold cyan]Analyzing Leads")
        self._analyze_all()

        # Filter by target location (US/Canada/Remote only)
        console.rule("[bold cyan]Filtering by Location")
        self._filter_by_location()

        self._print_summary()
        out = self.export()
        console.print(f"\n[bold green]Exported {len(self.all_leads)} leads to {out}")

        if self.config.google_sheet_id:
            self._upload_to_sheets()

        return self.all_leads

    def _analyze_all(self):
        """Run lead analysis on all scraped leads."""
        green = yellow = red = 0

        for lead in self.all_leads:
            try:
                analysis = self._analyzer.analyze(
                    title=lead.title,
                    description=lead.description,
                    budget=lead.budget,
                    url=lead.url,
                    platform=lead.platform,
                )
                self.all_analyses[lead.title] = analysis

                if analysis.priority == "GREEN":
                    green += 1
                elif analysis.priority == "YELLOW":
                    yellow += 1
                else:
                    red += 1
            except Exception as exc:
                logger.error("Analysis failed for '%s': %s", lead.title, exc)
                self.all_analyses[lead.title] = LeadAnalysis(
                    lead_score=0, priority="RED",
                    qualification_reason=f"Analysis failed: {exc}",
                )
                red += 1

        console.print(
            f"  [green]GREEN: {green}[/green] | "
            f"[yellow]YELLOW: {yellow}[/yellow] | "
            f"[red]RED: {red}[/red]"
        )

    # ──────────────────────────────────────────────────────────
    # Location filter
    # ──────────────────────────────────────────────────────────

    def _is_target_location(self, lead: JobLead, analysis: LeadAnalysis | None = None) -> bool:
        """Check if a lead's location matches target_locations (US/CA/Remote)."""
        target = set(loc.lower().strip() for loc in self.config.target_locations)
        _target_pats = [re.compile(r'\b' + re.escape(t) + r'\b') for t in target]

        us_states_lower = [
            "alabama", "alaska", "arizona", "arkansas", "california",
            "colorado", "connecticut", "delaware", "florida", "georgia",
            "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
            "kentucky", "louisiana", "maine", "maryland", "massachusetts",
            "michigan", "minnesota", "mississippi", "missouri", "montana",
            "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
            "new york", "north carolina", "north dakota", "ohio", "oklahoma",
            "oregon", "pennsylvania", "rhode island", "south carolina",
            "south dakota", "tennessee", "texas", "utah", "vermont",
            "virginia", "washington", "west virginia", "wisconsin", "wyoming",
            "district of columbia", "washington dc",
        ]
        ca_provinces_lower = [
            "ontario", "british columbia", "quebec", "alberta",
            "manitoba", "saskatchewan", "nova scotia", "new brunswick",
            "newfoundland", "prince edward island",
        ]
        us_ca_cities_lower = [
            "new york", "san francisco", "los angeles", "chicago", "boston",
            "austin", "seattle", "miami", "denver", "dallas", "houston",
            "atlanta", "portland", "phoenix", "san diego", "las vegas",
            "philadelphia", "nashville", "orlando", "toronto", "vancouver",
            "montreal", "calgary", "edmonton", "ottawa",
        ]

        # Collect all location signals
        location_sources = []

        # 1 – analysis location (most reliable, from LLM/extraction)
        if analysis and analysis.location and analysis.location != "Not Found":
            location_sources.append(analysis.location)

        # 2 – lead.location (from raw scraped data)
        if lead.location and lead.location != "Not Found":
            location_sources.append(lead.location)

        # 3 – check location sources
        for loc_str in location_sources:
            loc_lower = loc_str.lower()
            for pat in _target_pats:
                if pat.search(loc_lower):
                    return True
            for state in us_states_lower:
                if re.search(r'\b' + re.escape(state) + r'\b', loc_lower):
                    return True
            for prov in ca_provinces_lower:
                if re.search(r'\b' + re.escape(prov) + r'\b', loc_lower):
                    return True
            for city in us_ca_cities_lower:
                if re.search(r'\b' + re.escape(city) + r'\b', loc_lower):
                    return True

        # 4 – fallback: search description directly
        if lead.description and lead.description.strip():
            desc_lower = lead.description.lower()
            for state in us_states_lower:
                if re.search(r'\b' + re.escape(state) + r'\b', desc_lower):
                    return True
            for prov in ca_provinces_lower:
                if re.search(r'\b' + re.escape(prov) + r'\b', desc_lower):
                    return True
            for pat in _target_pats:
                if pat.search(desc_lower):
                    return True

        return False

    def _filter_by_location(self):
        """Remove leads that don't match target locations."""
        before = len(self.all_leads)
        kept = []
        dropped = 0
        for lead in self.all_leads:
            analysis = self.all_analyses.get(lead.title)
            if self._is_target_location(lead, analysis):
                kept.append(lead)
            else:
                dropped += 1

        self.all_leads = kept
        console.print(
            f"  [green]Kept: {len(kept)}[/green] | "
            f"[red]Dropped: {dropped}[/red] "
            f"(out of {before} total)"
        )

    def export(self) -> Path:
        """Write leads to CSV or JSON with analysis data."""
        out_dir = Path(self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if self.config.output_format == "json":
            path = out_dir / f"leads_{ts}.json"
            data = []
            for lead in self.all_leads:
                analysis = self.all_analyses.get(lead.title)
                row = self._lead_to_row(lead, analysis)
                data.append(row)
            path.write_text(json.dumps(data, indent=2, default=str))
        else:
            path = out_dir / f"leads_{ts}.csv"
            if not self.all_leads:
                path.write_text("No leads found.\n")
                return path
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=SHEET_HEADERS)
                writer.writeheader()
                for lead in self.all_leads:
                    analysis = self.all_analyses.get(lead.title)
                    writer.writerow(self._lead_to_row(lead, analysis))
        return path

    # ------------------------------------------------------------------
    # Google Sheets upload — separate tab per platform, color coded
    # ------------------------------------------------------------------

    def _upload_to_sheets(self):
        import gspread
        from google.oauth2.service_account import Credentials

        console.print("\n[bold yellow]Uploading to Google Sheets...[/bold yellow]")

        try:
            creds = Credentials.from_service_account_file(
                self.config.google_credentials_path,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
            gc = gspread.authorize(creds)
            sheet = gc.open_by_key(self.config.google_sheet_id)

            # Group leads by platform
            grouped: dict[str, list[JobLead]] = defaultdict(list)
            for lead in self.all_leads:
                sheet_name = PLATFORM_SHEET_MAP.get(lead.platform, lead.platform)
                grouped[sheet_name].append(lead)

            import time
            today_label = datetime.utcnow().strftime("%Y-%m-%d")

            for sheet_name, leads in grouped.items():
                # 1 – Upload to cumulative platform tab (filtered US/CA)
                self._upload_platform_sheet(sheet, sheet_name, leads)
                time.sleep(1)

                # 2 – Upload to date-based session tab (e.g. "Upwork 2026-07-21")
                session_tab = f"{sheet_name} {today_label}"
                self._upload_platform_sheet(sheet, session_tab, leads)
                time.sleep(1)

        except Exception as exc:
            console.print(f"[bold red]  Google Sheets upload failed: {exc}[/bold red]")
            logger.error("Sheets upload error: %s", exc)

    def _upload_platform_sheet(self, sheet, sheet_name: str, leads: list[JobLead]):
        from gspread.utils import rowcol_to_a1

        console.print(f"  [cyan]Sheet: {sheet_name} ({len(leads)} leads)[/cyan]")

        # Get or create worksheet
        try:
            worksheet = sheet.worksheet(sheet_name)
        except Exception:
            worksheet = sheet.add_worksheet(title=sheet_name, rows=1000, cols=25)

        # Get existing titles to avoid duplicates
        existing_titles = set()
        try:
            all_values = worksheet.get_all_values()
            if len(all_values) > 1:
                headers = [h.lower().strip() for h in all_values[0]]
                title_col = headers.index("job title") if "job title" in headers else 0
                existing_titles = {row[title_col] for row in all_values[1:] if row[title_col]}
        except Exception:
            pass

        # Write header if sheet is empty
        if not existing_titles:
            worksheet.update("A1", [SHEET_HEADERS])
            # Style header row
            try:
                header_range = f"A1:{rowcol_to_a1(1, len(SHEET_HEADERS))}"
                worksheet.format(header_range, {
                    "backgroundColor": COLOR_HEADER,
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                })
                # Freeze header row so it stays visible when scrolling
                worksheet.freeze("2")
                # Add auto-filter to header row (enables sort/filter dropdowns)
                worksheet.set_basic_filter()
            except Exception:
                pass

        new_rows = []
        new_analyses = []
        for lead in leads:
            if lead.title in existing_titles:
                continue
            analysis = self.all_analyses.get(lead.title)
            row = self._lead_to_row(lead, analysis)
            new_rows.append([row[h] for h in SHEET_HEADERS])
            new_analyses.append(analysis)

        if new_rows:
            existing_data_count = len(existing_titles)
            start_row = existing_data_count + 2
            end_row = start_row + len(new_rows) - 1

            worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")

            try:
                requests_list = []
                sheet_id = worksheet.id
                num_cols = len(SHEET_HEADERS)

                # Build row-formatting requests (batched as a single API call)
                for i, analysis in enumerate(new_analyses):
                    if analysis is None:
                        continue
                    row_num = start_row + i
                    color = COLOR_GREEN if analysis.priority == "GREEN" else (
                        COLOR_YELLOW if analysis.priority == "YELLOW" else COLOR_RED
                    )

                    fmt = {
                        "backgroundColor": color,
                    }
                    if analysis.priority == "GREEN":
                        fmt["textFormat"] = {"bold": True}

                    requests_list.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_num - 1,
                                "endRowIndex": row_num,
                                "startColumnIndex": 0,
                                "endColumnIndex": num_cols,
                            },
                            "cell": {"userEnteredFormat": fmt},
                            "fields": "userEnteredFormat(backgroundColor,textFormat)",
                        }
                    })

                    # Format Lead Score column as number
                    requests_list.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_num - 1,
                                "endRowIndex": row_num,
                                "startColumnIndex": 5,
                                "endColumnIndex": 6,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {"type": "NUMBER", "pattern": "0"}
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    })

                if requests_list:
                    worksheet.spreadsheet.batch_update({"requests": requests_list})

            except Exception as exc:
                logger.warning("Formatting failed: %s", exc)

            console.print(
                f"    [green]{len(new_rows)} new leads uploaded![/green]"
            )
        else:
            console.print(f"    [yellow]No new leads (all exist).[/yellow]")

    def _lead_to_row(self, lead: JobLead, analysis: LeadAnalysis | None = None) -> dict:
        """Convert a JobLead + LeadAnalysis to a sheet row dict."""
        a = analysis or LeadAnalysis()
        return {
            "Job Title": lead.title,
            "Job URL": lead.url,
            "Job Platform": lead.platform,
            "Date Posted": lead.posted_date,
            "Priority": a.priority,
            "Lead Score": str(a.lead_score),
            "Company Name": a.company_name,
            "Company Website": a.company_website,
            "Company Domain": a.company_domain,
            "Email": a.email,
            "Business Email": a.business_email,
            "Phone": a.phone,
            "LinkedIn URL": a.linkedin_url,
            "Decision-Maker Name": a.decision_maker_name,
            "Decision-Maker Title": a.decision_maker_title,
            "Budget": a.budget if a._found_budget else lead.budget,
            "Timeline": a.timeline,
            "Location": a.location or lead.location,
            "Industry": a.industry,
            "Technologies": a.technologies or lead.skills_required,
            "Services Required": a.services_required,
            "Qualification Reason": a.qualification_reason,
            "Full Job Description": (lead.description or "")[:1000],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _deduplicate(self, leads: list[JobLead]) -> list[JobLead]:
        new = []
        for lead in leads:
            if lead.title not in self._seen_titles:
                self._seen_titles.add(lead.title)
                new.append(lead)
        return new

    def _print_summary(self):
        table = Table(title="Lead Summary", show_lines=True)
        table.add_column("Platform", style="cyan")
        table.add_column("Keyword", style="cyan")
        table.add_column("Leads", justify="right", style="green")
        table.add_column("GREEN", justify="right", style="green")
        table.add_column("YELLOW", justify="right", style="yellow")
        table.add_column("RED", justify="right", style="red")

        from collections import Counter
        platform_data = defaultdict(lambda: {"count": Counter(), "green": 0, "yellow": 0, "red": 0})

        for l in self.all_leads:
            sheet_name = PLATFORM_SHEET_MAP.get(l.platform, l.platform)
            platform_data[sheet_name]["count"][l.keyword_searched] += 1
            analysis = self.all_analyses.get(l.title)
            if analysis:
                platform_data[sheet_name][analysis.priority.lower()] += 1

        total = total_g = total_y = total_r = 0
        for platform, data in sorted(platform_data.items()):
            for kw, count in data["count"].most_common():
                table.add_row(platform, kw, str(count), "", "", "")
                total += count
            table.add_row(
                f"  [dim]{platform} totals[/dim]", "",
                f"[bold]{sum(data['count'].values())}[/bold]",
                f"[green]{data['green']}[/green]",
                f"[yellow]{data['yellow']}[/yellow]",
                f"[red]{data['red']}[/red]",
            )
            total_g += data["green"]
            total_y += data["yellow"]
            total_r += data["red"]

        table.add_row(
            "[bold]TOTAL[/bold]", "",
            f"[bold]{total}[/bold]",
            f"[bold green]{total_g}[/bold green]",
            f"[bold yellow]{total_y}[/bold yellow]",
            f"[bold red]{total_r}[/bold red]",
        )
        console.print(table)

    def close(self):
        self._wayback.close()
        self._selenium.close()
        self._vollna.close()
        self._bark.close()
