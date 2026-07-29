"""Shared output schema and platform names."""

TIMING_HEADERS = [
    "Lead Found At",
    "Sheet Saved At",
    "Found-to-Sheet Seconds",
]
TIMING_INSERT_INDEX = 4

LEGACY_SHEET_HEADERS = [
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

SHEET_HEADERS = (
    LEGACY_SHEET_HEADERS[:TIMING_INSERT_INDEX]
    + TIMING_HEADERS
    + LEGACY_SHEET_HEADERS[TIMING_INSERT_INDEX:]
)

PLATFORM_SHEET_MAP = {
    "Upwork": "Upwork",
    "Upwork (Vollna)": "Vollna",
    "Freelancer": "Freelancer",
    "Guru": "Guru",
    "Upwork (Selenium)": "Upwork",
    "Bark.com": "Bark.com",
}

COLOR_GREEN = {"red": 0.85, "green": 0.92, "blue": 0.83}
COLOR_YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.8}
COLOR_RED = {"red": 1.0, "green": 0.85, "blue": 0.85}
COLOR_HEADER = {"red": 0.2, "green": 0.2, "blue": 0.2}

# Fixed pixel widths, in the same order as SHEET_HEADERS.
COLUMN_WIDTHS = [
    280, 260, 110, 115, 165, 165, 145, 90, 85, 160, 220, 160, 210,
    210, 140, 220, 170, 160, 120, 110, 150, 130, 220, 220, 300, 420,
]
