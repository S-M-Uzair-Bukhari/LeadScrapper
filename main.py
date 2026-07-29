#!/usr/bin/env python3
"""
Multi-Platform Lead Generator — CLI entry point.

Usage:
    python main.py                                         # all platforms
    python main.py -p upwork freelancer guru               # specific platforms
    python main.py -p upwork vollna -k "python" "django"  # custom keywords
    python main.py -k "web scraping" -r 20                 # 20 results per keyword
    python main.py -k "ai" --format json                   # JSON output
"""

import argparse
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler

from upwork_scraper.config import ScraperConfig, ALL_PLATFORMS
from upwork_scraper.engine import LeadEngine

console = Console()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scrape jobs from Upwork, Freelancer, Guru with client data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
platforms:
  upwork          = Upwork via Wayback Machine (title, budget, skills)
  upwork_selenium = Upwork via Selenium (authenticated, needs Upwork login)
  vollna          = Vollna.com (Upwork client data: rank, spending, rating)
  freelancer      = Freelancer.com (title, budget, skills)
  guru            = Guru.com (title, budget, skills)
  all             = All platforms (default)

examples:
  python main.py                                         # all platforms
  python main.py -p upwork freelancer                   # Upwork + Freelancer only
  python main.py -p guru -k "python" "django"           # Guru only, custom keywords
  python main.py -k "web scraping" "lead gen" -r 20     # all platforms, 20 each
  python main.py --format json                          # JSON output
        """,
    )
    p.add_argument(
        "-k", "--keywords",
        nargs="+",
        help="Search keywords (default: python, data entry, lead gen, web scraping)",
    )
    p.add_argument(
        "-p", "--platforms",
        nargs="+",
        choices=ALL_PLATFORMS + ["all"],
        default=None,
        help="Platforms to scrape (default: all)",
    )
    p.add_argument(
        "-r", "--results",
        type=int,
        default=None,
        help="Max results per keyword (default: 50)",
    )
    p.add_argument(
        "--format",
        choices=["csv", "json"],
        default=None,
        help="Output format (default: csv)",
    )
    p.add_argument(
        "--delay",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Delay range in seconds between requests",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return p.parse_args()


def main():
    args = parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    config = ScraperConfig()
    if args.keywords:
        config.keywords = args.keywords
    if args.platforms:
        config.platforms = args.platforms
    if args.results is not None:
        config.max_results_per_keyword = args.results
    if args.format:
        config.output_format = args.format
    if args.delay:
        config.min_delay, config.max_delay = args.delay

    engine = LeadEngine(config)
    try:
        leads = engine.run()
        sys.exit(0 if leads else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.")
        sys.exit(130)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
