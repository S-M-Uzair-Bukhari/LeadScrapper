"""Final CSV and JSON export."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..pipeline.processor import ProcessedLead
from .rows import processed_lead_to_row
from .schema import SHEET_HEADERS


class LocalExporter:
    def __init__(self, output_dir: str, output_format: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_format = output_format

    def export(self, items: list[ProcessedLead], run_id: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "json" if self.output_format == "json" else "csv"
        path = self.output_dir / f"leads_{run_id}.{suffix}"
        rows = [processed_lead_to_row(item) for item in items]

        if suffix == "json":
            path.write_text(
                json.dumps(rows, indent=2, default=str),
                encoding="utf-8",
            )
            return path

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        return path
