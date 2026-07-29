#!/usr/bin/env python3
"""
Filter existing CSV leads — keep only US/Canada/Remote leads.
Reads all CSVs from output/, deduplicates, writes a single filtered CSV.

Usage:
    python filter_us_ca.py                         # default: reads output/*.csv
    python filter_us_ca.py -o filtered_leads.csv   # custom output path
"""

import csv
import re
import sys
import argparse
from pathlib import Path

OUTPUT_DIR = Path("output")

US_STATES_LOWER = [
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

CA_PROVINCES_LOWER = [
    "ontario", "british columbia", "quebec", "alberta",
    "manitoba", "saskatchewan", "nova scotia", "new brunswick",
    "newfoundland", "prince edward island",
]

US_CA_CITIES_LOWER = [
    "new york", "san francisco", "los angeles", "chicago", "boston",
    "austin", "seattle", "miami", "denver", "dallas", "houston",
    "atlanta", "portland", "phoenix", "san diego", "las vegas",
    "philadelphia", "nashville", "orlando", "toronto", "vancouver",
    "montreal", "calgary", "edmonton", "ottawa",
]

US_TIMEZONES_LOWER = [
    "est", "pst", "cst", "mst", "eastern standard time",
    "pacific standard time", "central standard time", "mountain standard time",
    "gmt-05", "gmt-08", "gmt-04", "gmt-07", "gmt-06",
]

# Known non-US/CA countries/regions — if Location column contains these, reject immediately
FOREIGN_LOCATIONS_LOWER = [
    "united kingdom", "uk", "australia", "germany", "india", "pakistan",
    "london", "berlin", "dubai", "singapore", "europe", "asia",
    "united arab emirates", "uae", "saudi arabia", "france", "spain",
    "italy", "netherlands", "switzerland", "sweden", "norway", "denmark",
    "finland", "belgium", "austria", "ireland", "poland", "portugal",
    "brazil", "mexico", "japan", "south korea", "china", "hong kong",
    "new zealand", "south africa", "nigeria", "kenya", "paris",
    "amsterdam", "sydney", "melbourne", "mumbai", "delhi", "bangalore",
    "hyderabad", "abu dhabi", "riyadh", "doha", "zurich", "geneva",
    "bangladesh", "indonesia", "philippines", "turkey", "egypt",
    "argentina", "chile", "colombia", "peru", "romania", "poland",
    "czech", "hungary", "ukraine", "russia", "thailand", "vietnam",
    "malaysia", "korea", "south america",
]


def is_foreign_location(loc: str) -> bool:
    for country in FOREIGN_LOCATIONS_LOWER:
        if re.search(r'\b' + re.escape(country) + r'\b', loc):
            return True
    return False


def is_target_location(location_str: str) -> bool:
    if not location_str or location_str.strip() in ("", "Not Found"):
        return False
    loc = location_str.lower().strip()

    # Direct country / remote match (word boundaries to avoid false matches)
    target_exact = [
        r'\busa\b', r'\bu\.s\b', r'\bu\.s\.a\b', r'\bunited states\b',
        r'\bcanada\b', r'\bremote\b', r'\bamericas\b',
    ]
    for pat in target_exact:
        if re.search(pat, loc):
            return True

    for state in US_STATES_LOWER:
        if re.search(r'\b' + re.escape(state) + r'\b', loc):
            return True
    for prov in CA_PROVINCES_LOWER:
        if re.search(r'\b' + re.escape(prov) + r'\b', loc):
            return True
    for city in US_CA_CITIES_LOWER:
        if re.search(r'\b' + re.escape(city) + r'\b', loc):
            return True
    for tz in US_TIMEZONES_LOWER:
        if re.search(r'\b' + re.escape(tz) + r'\b', loc):
            return True
    return False


def has_location_in_text(text: str) -> bool:
    """Strict fallback — only match if location appears in a location context."""
    if not text:
        return False
    t = text.lower()

    # Location-context patterns: "based in", "located in", "📍", "office in", etc.
    context_pats = [
        # "based in the US", "located in California", "office in Toronto"
        r'(?:based|located|office|headquarters|remote|onsite|on-site|hybrid)\s+(?:in|at|:)\s*[^.]*\b(united states|usa|canada|remote)\b',
        r'(?:based|located|office|headquarters|remote|onsite|on-site|hybrid)\s+(?:in|at|:)\s*[^.]*\b(' + r'|'.join(US_STATES_LOWER) + r')\b',
        r'(?:based|located|office|headquarters|remote|onsite|on-site|hybrid)\s+(?:in|at|:)\s*[^.]*\b(' + r'|'.join(CA_PROVINCES_LOWER) + r')\b',
        # 📍 marker (common in Upwork posts)
        r'📍\s*[^.\n]*\b(united states|usa|canada|remote)\b',
        r'📍\s*[^.\n]*(' + r'|'.join(US_CA_CITIES_LOWER) + r')',
        # "Remote (US)", "Remote (United States)", "Remote - US"
        r'remote\s*[\(\[-]\s*(united states|usa|canada|us)',
        # "US only", "US based", "US clients", "US timezone"
        r'\bunited states\s*(?:only|based|client|timezone|hours)\b',
        r'\busa\s*(?:only|based|client|timezone|hours)\b',
        r'\bcanada\s*(?:only|based|client|timezone|hours)\b',
        # Explicit "US timezone" / "EST / PST" patterns
        r'(?:est|pst|cst|mst|eastern|pacific|central|mountain)\s*(?:standard\s*)?(?:time|timezone|hours)',
    ]
    for pat in context_pats:
        if re.search(pat, t, re.IGNORECASE):
            return True

    # Direct standalone remote mention with no other country context
    if re.search(r'\bremote\b', t) and not re.search(r'\b(india|uk|london|europe|asia|australia|dubai|germany|france|spain|italy|china|japan|singapore)\b', t):
        return True

    return False


def find_column(headers: list[str], *names: str) -> int | None:
    """Find column index by any of the given names (case-insensitive)."""
    h_lower = [h.lower().strip() for h in headers]
    for name in names:
        nl = name.lower().strip()
        if nl in h_lower:
            return h_lower.index(nl)
    return None


def main():
    parser = argparse.ArgumentParser(description="Filter CSV leads to US/Canada only")
    parser.add_argument("-o", "--output", default="output/us_ca_leads_filtered.csv",
                        help="Output CSV path (default: output/us_ca_leads_filtered.csv)")
    parser.add_argument("files", nargs="*",
                        help="CSV files to process (default: all output/*.csv)")
    args = parser.parse_args()

    csv_files = []
    if args.files:
        csv_files = [Path(f) for f in args.files]
    else:
        csv_files = sorted(OUTPUT_DIR.glob("*.csv"))

    if not csv_files:
        print("No CSV files found.")
        sys.exit(1)

    combined_headers = [
        "Job Title", "Job URL", "Job Platform", "Date Posted", "Priority",
        "Lead Score", "Company Name", "Company Website", "Company Domain",
        "Email", "Business Email", "Phone", "LinkedIn URL",
        "Decision-Maker Name", "Decision-Maker Title", "Budget", "Timeline",
        "Location", "Industry", "Technologies", "Services Required",
        "Qualification Reason", "Full Job Description",
    ]

    seen_titles: set[str] = set()
    kept_rows: list[dict] = []
    file_stats: dict[str, int] = {}

    for fpath in csv_files:
        print(f"Reading: {fpath.name} ...", end=" ")
        try:
            with open(fpath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    print("SKIP (no headers)")
                    continue
                rows = list(reader)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        total = len(rows)
        file_kept = 0
        headers = reader.fieldnames

        loc_col = find_column(headers, "location")
        desc_col = find_column(headers, "full job description", "description")
        llm_col = find_column(headers, "llm summary", "summary")
        title_col = find_column(headers, "job title", "title")

        for row in rows:
            title = row[headers[title_col]].strip() if title_col is not None else ""
            if not title or title in seen_titles:
                continue

            location = row[headers[loc_col]].strip() if loc_col is not None else ""
            description = row[headers[desc_col]].strip() if desc_col is not None else ""
            llm = row[headers[llm_col]].strip() if llm_col is not None else ""

            loc_lower = location.lower().strip()

            # If location mentions a known foreign country, reject immediately
            if loc_lower and loc_lower not in ("", "not found") and is_foreign_location(loc_lower):
                continue

            # Check location field for US/CA/Remote
            if is_target_location(location):
                seen_titles.add(title)
                kept_rows.append(_normalize(row, headers, combined_headers))
                file_kept += 1
                continue

            # Fallback: only if location is truly empty/unknown
            if loc_lower in ("", "not found"):
                combined_text = f"{description} {llm} {title}"
                if has_location_in_text(combined_text):
                    seen_titles.add(title)
                    norm = _normalize(row, headers, combined_headers)
                    norm["Location"] = "Remote" if re.search(r'\bremote\b', combined_text.lower()) else "United States (inferred)"
                    kept_rows.append(norm)
                    file_kept += 1

        file_stats[fpath.name] = (total, file_kept)
        print(f"{total} total, {file_kept} kept")

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=combined_headers)
        writer.writeheader()
        writer.writerows(kept_rows)

    total_input = sum(s[0] for s in file_stats.values())
    total_kept = len(kept_rows)

    print("\n" + "=" * 55)
    print(f"Total input:  {total_input}")
    print(f"Total kept:   {total_kept}  (US/Canada/Remote)")
    print(f"Total output: {out_path}")
    print("=" * 55)

    for fname, (total, kept) in sorted(file_stats.items()):
        pct = (kept / total * 100) if total else 0
        print(f"  {fname:40s}  {total:6d}  →  {kept:5d}  ({pct:.1f}%)")


def _normalize(row: dict, src_headers: list[str], target_headers: list[str]) -> dict:
    """Map source row to target headers, filling missing with empty string."""
    out = {h: "" for h in target_headers}
    src_lower = {h.lower().strip(): h for h in src_headers}
    for th in target_headers:
        tl = th.lower().strip()
        if tl in src_lower:
            out[th] = row.get(src_lower[tl], "")
    return out


if __name__ == "__main__":
    main()
