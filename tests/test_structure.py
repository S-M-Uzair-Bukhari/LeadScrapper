"""Offline tests for the refactored structural components."""

from __future__ import annotations

import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from upwork_scraper.analyzer import LeadAnalysis
from upwork_scraper.config import ScraperConfig
from upwork_scraper.exporters.sheets import SheetsBatchWriter
from upwork_scraper.exporters.rows import processed_lead_to_row
from upwork_scraper.models import JobLead
from upwork_scraper.orchestration.engine import LeadEngine
from upwork_scraper.pipeline.deduplicator import RunDeduplicator
from upwork_scraper.pipeline.location_filter import LocationFilter
from upwork_scraper.pipeline.processor import LeadProcessor, ProcessedLead
from upwork_scraper.platforms.base import PlatformAdapter


class _AnalyzerStub:
    def __init__(self, location: str = "Remote") -> None:
        self.location = location

    def analyze(self, **_: str) -> LeadAnalysis:
        return LeadAnalysis(
            location=self.location,
            lead_score=50,
            priority="GREEN",
        )


class _RepositoryStub:
    def mark_uploaded(self, _: list[str]) -> None:
        pass


class _SheetsWriterProbe(SheetsBatchWriter):
    def __init__(self) -> None:
        config = SimpleNamespace(google_sheet_id="test", sheets_batch_size=10)
        super().__init__(config, _RepositoryStub())
        self.flush_calls: list[tuple[str, int | None]] = []

    def _flush_sheet(self, sheet_name: str, limit: int | None = None) -> None:
        self.flush_calls.append((sheet_name, limit))


class _QuotaError(Exception):
    code = 429

    def __init__(self, retry_after: str | None = None) -> None:
        self.response = SimpleNamespace(
            status_code=429,
            headers={"Retry-After": retry_after} if retry_after else {},
        )


class _FailingSheetsWriter(SheetsBatchWriter):
    def __init__(self) -> None:
        config = SimpleNamespace(
            google_sheet_id="test",
            sheets_batch_size=10,
            sheets_retry_attempts=1,
            sheets_quota_cooldown=60,
        )
        super().__init__(config, _RepositoryStub())
        self.append_attempts = 0

    def _append_to_tab(self, tab_name: str, batch: list) -> None:
        self.append_attempts += 1
        raise _QuotaError()


class StructuralPipelineTests(unittest.TestCase):
    def test_deduplicates_titles_case_insensitively(self) -> None:
        deduplicator = RunDeduplicator()
        first = JobLead(title="React Developer")
        duplicate = JobLead(title="  react   developer ")

        self.assertTrue(deduplicator.accept(first))
        self.assertFalse(deduplicator.accept(duplicate))

    def test_accepts_remote_lead(self) -> None:
        processor = LeadProcessor(
            analyzer=_AnalyzerStub(),
            deduplicator=RunDeduplicator(),
            location_filter=LocationFilter(
                ["United States", "Canada", "Remote"]
            ),
        )

        result = processor.process(
            JobLead(title="Build a dashboard", description="Relevant project")
        )

        self.assertIsNotNone(result)

    def test_rejects_non_target_location(self) -> None:
        processor = LeadProcessor(
            analyzer=_AnalyzerStub(location="London, United Kingdom"),
            deduplicator=RunDeduplicator(),
            location_filter=LocationFilter(
                ["United States", "Canada", "Remote"]
            ),
        )

        result = processor.process(
            JobLead(title="Build an API", description="Onsite in London")
        )

        self.assertIsNone(result)

    def test_sheets_upload_triggers_at_ten_qualified_leads(self) -> None:
        writer = _SheetsWriterProbe()
        analysis = LeadAnalysis(priority="GREEN", lead_score=50)

        for index in range(9):
            writer.add(
                ProcessedLead(
                    JobLead(title=f"Lead {index}", platform="Upwork"),
                    analysis,
                ),
                f"lead-{index}",
            )
        self.assertEqual(writer.flush_calls, [])

        writer.add(
            ProcessedLead(
                JobLead(title="Lead 9", platform="Upwork"),
                analysis,
            ),
            "lead-9",
        )
        self.assertEqual(writer.flush_calls, [("Upwork", 10)])

    def test_sheets_write_retries_429_with_exponential_backoff(self) -> None:
        writer = _SheetsWriterProbe()
        writer.config.sheets_retry_attempts = 3
        writer.config.sheets_retry_base_delay = 2
        writer.config.sheets_retry_max_delay = 10
        writer.config.sheets_min_write_interval = 0
        now = [0.0]
        sleeps = []
        attempts = [0]
        writer._monotonic = lambda: now[0]

        def fake_sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        def flaky_write() -> str:
            attempts[0] += 1
            if attempts[0] < 3:
                raise _QuotaError()
            return "ok"

        writer._sleep = fake_sleep
        result = writer._write("test operation", flaky_write)

        self.assertEqual(result, "ok")
        self.assertEqual(attempts[0], 3)
        self.assertEqual(sleeps, [2, 4])

    def test_failed_batch_enters_cooldown_without_losing_buffer(self) -> None:
        writer = _FailingSheetsWriter()
        now = [100.0]
        writer._monotonic = lambda: now[0]
        analysis = LeadAnalysis(priority="GREEN", lead_score=50)

        for index in range(10):
            writer.add(
                ProcessedLead(
                    JobLead(title=f"Quota Lead {index}", platform="Upwork"),
                    analysis,
                ),
                f"quota-{index}",
            )

        self.assertEqual(writer.append_attempts, 1)
        self.assertEqual(len(writer._buffers["Upwork"]), 10)
        self.assertEqual(writer._retry_not_before["Upwork"], 160.0)

        writer.add(
            ProcessedLead(
                JobLead(title="Quota Lead 10", platform="Upwork"),
                analysis,
            ),
            "quota-10",
        )
        self.assertEqual(writer.append_attempts, 1)
        self.assertEqual(len(writer._buffers["Upwork"]), 11)

    def test_export_row_records_found_to_sheet_duration(self) -> None:
        item = ProcessedLead(
            JobLead(
                title="Timed lead",
                scraped_at="2026-07-29T10:00:00+00:00",
            ),
            LeadAnalysis(priority="GREEN", lead_score=50),
        )

        row = processed_lead_to_row(
            item,
            sheet_saved_at=datetime(
                2026, 7, 29, 10, 0, 12, 500000, tzinfo=timezone.utc
            ),
        )

        self.assertEqual(row["Lead Found At"], "2026-07-29T10:00:00+00:00")
        self.assertEqual(row["Sheet Saved At"], "2026-07-29T10:00:12+00:00")
        self.assertEqual(row["Found-to-Sheet Seconds"], "12.50")

    def test_engine_processes_keyword_results_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                keywords=["react", "shopify"],
                platforms=[],
                output_dir=temp_dir,
                database_path=str(Path(temp_dir) / "leads.db"),
                google_sheet_id="",
            )
            engine = LeadEngine(config)

            def scrape(keyword: str) -> list[JobLead]:
                return [
                    JobLead(
                        title=f"{keyword.title()} Developer",
                        platform="Test Platform",
                        description=(
                            "Location: Remote. We need web development services."
                        ),
                    )
                ]

            engine._adapters = {
                "test": PlatformAdapter("test", scrape)
            }
            try:
                leads = engine.run()
            finally:
                engine.close()

            self.assertEqual(len(leads), 2)
            exports = list(Path(temp_dir).glob("leads_*.csv"))
            self.assertEqual(len(exports), 1)
            self.assertTrue((Path(temp_dir) / "leads.db").exists())


if __name__ == "__main__":
    unittest.main()
