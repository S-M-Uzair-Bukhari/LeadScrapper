#!/usr/bin/env python3
"""Upload existing CSV leads to Google Sheets."""
import csv
import os
import logging
from pathlib import Path
from collections import defaultdict

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")

SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
CREDS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "service-account.json")
CSV_PATH = "output/leads_20260716_211534.csv"

SHEET_HEADERS = [
    "Job Title", "Job URL", "Job Platform", "Date Posted", "Priority",
    "Lead Score", "Company Name", "Company Website", "Company Domain",
    "Email", "Business Email", "Phone", "LinkedIn URL",
    "Decision-Maker Name", "Decision-Maker Title", "Budget", "Timeline",
    "Location", "Industry", "Technologies", "Services Required",
    "Qualification Reason", "Full Job Description",
]

PLATFORM_SHEET_MAP = {
    "Bark.com": "Bark.com",
    "Freelancer": "Freelancer",
    "Guru": "Guru",
    "Upwork": "Upwork",
    "Upwork (Vollna)": "Vollna",
    "Upwork (Selenium)": "Upwork",
}

COLOR_GREEN = {"red": 0.85, "green": 0.92, "blue": 0.83}
COLOR_YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.8}
COLOR_RED = {"red": 1.0, "green": 0.85, "blue": 0.85}
COLOR_HEADER = {"red": 0.2, "green": 0.2, "blue": 0.2}

def main():
    if not SHEET_ID:
        print("GOOGLE_SHEET_ID not set in .env")
        return

    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Loaded {len(rows)} leads from {CSV_PATH}")

    creds = Credentials.from_service_account_file(
        CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)

    grouped = defaultdict(list)
    for row in rows:
        platform = row.get("Job Platform", "")
        sheet_name = PLATFORM_SHEET_MAP.get(platform, platform)
        grouped[sheet_name].append(row)

    for sheet_name, leads in grouped.items():
        print(f"\n{sheet_name}: {len(leads)} leads")
        try:
            worksheet = sheet.worksheet(sheet_name)
        except Exception:
            worksheet = sheet.add_worksheet(title=sheet_name, rows=1000, cols=25)

        existing_titles = set()
        try:
            all_values = worksheet.get_all_values()
            if len(all_values) > 1:
                headers = [h.lower().strip() for h in all_values[0]]
                title_col = headers.index("job title") if "job title" in headers else 0
                existing_titles = {row[title_col] for row in all_values[1:] if row[title_col]}
        except Exception:
            pass

        new_rows = []
        for row in leads:
            if row.get("Job Title", "") in existing_titles:
                continue
            new_rows.append([row.get(h, "") for h in SHEET_HEADERS])

        if not new_rows:
            print("  No new leads to upload.")
            continue

        if not existing_titles:
            worksheet.update("A1", [SHEET_HEADERS])
            header_range = f"A1:{chr(64 + len(SHEET_HEADERS))}1"
            worksheet.format(header_range, {
                "backgroundColor": COLOR_HEADER,
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
            })
            try:
                worksheet.freeze("2")
                worksheet.set_basic_filter()
            except Exception:
                pass

        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"  Uploaded {len(new_rows)} new leads.")
        import time
        time.sleep(2)

    print("\nDone!")

if __name__ == "__main__":
    main()
