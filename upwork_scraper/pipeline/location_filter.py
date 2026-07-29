"""US, Canada, and remote lead filtering."""

from __future__ import annotations

import re

from ..analyzer import LeadAnalysis
from ..models import JobLead

US_STATES = (
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    "washington dc",
)

CA_PROVINCES = (
    "ontario", "british columbia", "quebec", "alberta", "manitoba",
    "saskatchewan", "nova scotia", "new brunswick", "newfoundland",
    "prince edward island",
)

US_CA_CITIES = (
    "new york", "san francisco", "los angeles", "chicago", "boston",
    "austin", "seattle", "miami", "denver", "dallas", "houston",
    "atlanta", "portland", "phoenix", "san diego", "las vegas",
    "philadelphia", "nashville", "orlando", "toronto", "vancouver",
    "montreal", "calgary", "edmonton", "ottawa",
)


class LocationFilter:
    def __init__(self, target_locations: list[str]) -> None:
        targets = (item.casefold().strip() for item in target_locations)
        self._target_patterns = tuple(
            re.compile(r"\b" + re.escape(item) + r"\b")
            for item in targets
            if item
        )

    @staticmethod
    def _contains(value: str, candidates: tuple[str, ...]) -> bool:
        return any(
            re.search(r"\b" + re.escape(candidate) + r"\b", value)
            for candidate in candidates
        )

    def matches(
        self, lead: JobLead, analysis: LeadAnalysis | None = None
    ) -> bool:
        sources: list[str] = []
        if analysis and analysis.location not in ("", "Not Found"):
            sources.append(analysis.location)
        if lead.location not in ("", "Not Found"):
            sources.append(lead.location)

        for source in sources:
            value = source.casefold()
            if any(pattern.search(value) for pattern in self._target_patterns):
                return True
            if self._contains(value, US_STATES):
                return True
            if self._contains(value, CA_PROVINCES):
                return True
            if self._contains(value, US_CA_CITIES):
                return True

        description = (lead.description or "").casefold()
        if not description:
            return False
        if any(pattern.search(description) for pattern in self._target_patterns):
            return True
        if self._contains(description, US_STATES):
            return True
        return self._contains(description, CA_PROVINCES)
