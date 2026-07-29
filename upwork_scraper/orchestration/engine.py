"""Concurrent lead-generation orchestration."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from ..analyzer import LeadAnalysis, LeadAnalyzer
from ..config import ScraperConfig
from ..exporters.local import LocalExporter
from ..exporters.schema import PLATFORM_SHEET_MAP
from ..exporters.sheets import SheetsBatchWriter
from ..models import JobLead
from ..pipeline.deduplicator import RunDeduplicator
from ..pipeline.location_filter import LocationFilter
from ..pipeline.processor import LeadProcessor, ProcessedLead
from ..platforms.registry import build_platform_adapters
from ..storage.sqlite_repository import SQLiteLeadRepository
from .events import KeywordResult, PlatformFinished
from .scheduler import PlatformScheduler

logger = logging.getLogger(__name__)
console = Console()


class LeadEngine:
    """Coordinate platform workers, processing, persistence, and output."""

    def __init__(self, config: ScraperConfig | None = None) -> None:
        self.config = config or ScraperConfig()
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.all_leads: list[JobLead] = []
        self.all_analyses: dict[str, LeadAnalysis] = {}
        self._processed: list[ProcessedLead] = []
        self._closed = False

        self._adapters = build_platform_adapters(self.config)
        self._deduplicator = RunDeduplicator()
        self._processor = LeadProcessor(
            LeadAnalyzer(),
            self._deduplicator,
            LocationFilter(self.config.target_locations),
        )
        self._repository = SQLiteLeadRepository(
            self.config.database_path, self.run_id
        )
        self._sheets = SheetsBatchWriter(self.config, self._repository)
        self._local_exporter = LocalExporter(
            self.config.output_dir, self.config.output_format
        )

    def run(self) -> list[JobLead]:
        platforms = list(self._adapters)
        console.rule("[bold green]Multi-Platform Lead Generator")
        console.print(f"Platforms: [cyan]{', '.join(platforms)}[/cyan]")
        console.print(
            f"Execution: [cyan]{self.config.max_platform_workers} "
            "platform workers; "
            f"{self.config.max_browser_workers} browser slots; "
            "keywords sequential per platform[/cyan]"
        )
        console.print(
            f"Sheets batch: [cyan]{self.config.sheets_batch_size} "
            "qualified leads[/cyan]"
        )

        scheduler = PlatformScheduler(
            adapters=self._adapters,
            keywords=self.config.keywords,
            max_workers=self.config.max_platform_workers,
            max_browser_workers=self.config.max_browser_workers,
            queue_size=self.config.event_queue_size,
        )
        worker_sheet_labels: dict[str, set[str]] = defaultdict(set)

        for event in scheduler.events():
            if isinstance(event, KeywordResult):
                self._handle_keyword_result(event, worker_sheet_labels)
            elif isinstance(event, PlatformFinished):
                for label in worker_sheet_labels[event.platform_worker]:
                    self._sheets.flush_platform(label)
                console.print(
                    f"[green]Platform completed:[/green] "
                    f"{event.platform_worker}"
                )

        self._sheets.flush_all()
        path = self._local_exporter.export(self._processed, self.run_id)
        self._print_summary()
        console.print(
            f"\n[bold green]Exported {len(self._processed)} qualified "
            f"leads to {path}[/bold green]"
        )
        return self.all_leads

    def _handle_keyword_result(
        self,
        event: KeywordResult,
        worker_sheet_labels: dict[str, set[str]],
    ) -> None:
        if event.error:
            logger.warning(
                "%s failed for '%s': %s",
                event.platform_worker,
                event.keyword,
                event.error,
            )
            return

        accepted = 0
        for lead in event.leads:
            lead.keyword_searched = event.keyword
            item = self._processor.process(lead)
            if item is None:
                continue

            dedup_key = self._deduplicator.key(lead)
            self._repository.save(
                event.platform_worker,
                event.keyword,
                item,
                dedup_key,
            )
            self._processed.append(item)
            self.all_leads.append(lead)
            self.all_analyses[lead.title] = item.analysis
            worker_sheet_labels[event.platform_worker].add(lead.platform)
            self._sheets.add(item, dedup_key)
            accepted += 1

        console.print(
            f"  {event.platform_worker} | {event.keyword}: "
            f"{len(event.leads)} scraped, "
            f"[green]{accepted} qualified/new[/green]"
        )

    def _print_summary(self) -> None:
        table = Table(title="Qualified Lead Summary", show_lines=True)
        table.add_column("Platform", style="cyan")
        table.add_column("Leads", justify="right")
        table.add_column("GREEN", justify="right", style="green")
        table.add_column("YELLOW", justify="right", style="yellow")
        table.add_column("RED", justify="right", style="red")

        summary: dict[str, Counter] = defaultdict(Counter)
        for item in self._processed:
            platform = PLATFORM_SHEET_MAP.get(
                item.lead.platform, item.lead.platform
            )
            summary[platform]["total"] += 1
            summary[platform][item.analysis.priority] += 1

        for platform, counts in sorted(summary.items()):
            table.add_row(
                platform,
                str(counts["total"]),
                str(counts["GREEN"]),
                str(counts["YELLOW"]),
                str(counts["RED"]),
            )
        console.print(table)

    def close(self) -> None:
        if self._closed:
            return
        for adapter in self._adapters.values():
            try:
                adapter.close()
            except Exception as exc:
                logger.warning("Failed to close %s: %s", adapter.name, exc)
        self._repository.close()
        self._closed = True
