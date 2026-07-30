"""Composable processing stages applied to each scraped lead."""

from __future__ import annotations

from dataclasses import dataclass

from ..analyzer import LeadAnalysis, LeadAnalyzer
from ..models import JobLead
from .deduplicator import RunDeduplicator
from .location_filter import LocationFilter
from .recency_filter import RecencyFilter


@dataclass(frozen=True)
class ProcessedLead:
    lead: JobLead
    analysis: LeadAnalysis


class LeadProcessor:
    def __init__(
        self,
        analyzer: LeadAnalyzer,
        deduplicator: RunDeduplicator,
        location_filter: LocationFilter,
        recency_filter: RecencyFilter | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._deduplicator = deduplicator
        self._location_filter = location_filter
        self._recency_filter = recency_filter or RecencyFilter(None)

    def process(self, lead: JobLead) -> ProcessedLead | None:
        if not self._recency_filter.matches(lead):
            return None
        if not self._deduplicator.accept(lead):
            return None

        analysis = self._analyzer.analyze(
            title=lead.title,
            description=lead.description,
            budget=lead.budget,
            url=lead.url,
            platform=lead.platform,
        )
        if not self._location_filter.matches(lead, analysis):
            return None
        return ProcessedLead(lead=lead, analysis=analysis)
