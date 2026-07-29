"""Offline tests for deterministic Google Sheets headers and layout."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from upload_sheets import (
    COLUMN_WIDTHS,
    LEGACY_SHEET_HEADERS,
    SHEET_HEADERS,
    TIMING_INSERT_INDEX,
    _apply_fixed_layout,
    _ensure_headers,
)
from upwork_scraper.exporters.sheets import SheetsBatchWriter


class _SpreadsheetFake:
    def __init__(self, worksheet=None) -> None:
        self.requests = []
        self.worksheet = worksheet

    def batch_update(self, body: dict) -> None:
        self.requests.extend(body["requests"])
        if self.worksheet is None:
            return
        for request in body["requests"]:
            insertion = request.get("insertDimension")
            if not insertion:
                continue
            dimension_range = insertion["range"]
            if dimension_range["dimension"] != "COLUMNS":
                continue
            start = dimension_range["startIndex"]
            count = dimension_range["endIndex"] - start
            for row in self.worksheet.values:
                row[start:start] = [""] * count


class _RepositoryFake:
    def mark_uploaded(self, dedup_keys: list[str]) -> None:
        pass


class _WorksheetFake:
    def __init__(self, values: list[list[str]]) -> None:
        self.values = [list(row) for row in values]
        self.col_count = 25
        self.row_count = 1000
        self.id = 123
        self.title = "Test"
        self.spreadsheet = _SpreadsheetFake(self)
        self.formatted_ranges = []

    def get_all_values(self) -> list[list[str]]:
        return [list(row) for row in self.values]

    def add_cols(self, count: int) -> None:
        self.col_count += count

    def update(self, *, range_name: str, values: list[list[str]]) -> None:
        if self.values:
            self.values[0] = list(values[0])
        else:
            self.values = [list(values[0])]

    def insert_row(
        self,
        values: list[str],
        index: int,
        value_input_option: str,
    ) -> None:
        self.values.insert(index - 1, list(values))

    def format(self, range_name: str, cell_format: dict) -> None:
        self.formatted_ranges.append((range_name, cell_format))


class UploadSheetLayoutTests(unittest.TestCase):
    def test_empty_worksheet_receives_headers(self) -> None:
        worksheet = _WorksheetFake([])

        values = _ensure_headers(worksheet)

        self.assertEqual(values[0], SHEET_HEADERS)

    def test_headerless_data_is_preserved_below_inserted_header(self) -> None:
        existing_lead = ["Existing lead", "https://example.com"]
        worksheet = _WorksheetFake([existing_lead])

        values = _ensure_headers(worksheet)

        self.assertEqual(values[0], SHEET_HEADERS)
        self.assertEqual(values[1], existing_lead)

    def test_legacy_sheet_inserts_timing_columns_without_shifting_data(self) -> None:
        legacy_row = [f"value-{index}" for index in range(len(LEGACY_SHEET_HEADERS))]
        worksheet = _WorksheetFake([LEGACY_SHEET_HEADERS, legacy_row])

        values = _ensure_headers(worksheet)

        self.assertEqual(values[0], SHEET_HEADERS)
        self.assertEqual(
            values[1][TIMING_INSERT_INDEX:TIMING_INSERT_INDEX + 3],
            ["", "", ""],
        )
        self.assertEqual(
            values[1][TIMING_INSERT_INDEX + 3],
            legacy_row[TIMING_INSERT_INDEX],
        )

    def test_layout_uses_fixed_columns_rows_and_clipped_text(self) -> None:
        worksheet = _WorksheetFake([SHEET_HEADERS])

        _apply_fixed_layout(worksheet)

        requests = worksheet.spreadsheet.requests
        column_requests = [
            request
            for request in requests
            if request.get("updateDimensionProperties", {})
            .get("range", {})
            .get("dimension") == "COLUMNS"
        ]
        self.assertEqual(len(column_requests), len(COLUMN_WIDTHS))

        repeat_cell = next(
            request["repeatCell"]
            for request in requests
            if "repeatCell" in request
        )
        self.assertEqual(
            repeat_cell["cell"]["userEnteredFormat"]["wrapStrategy"],
            "CLIP",
        )

    def test_runtime_writer_uses_the_same_fixed_layout(self) -> None:
        worksheet = _WorksheetFake([SHEET_HEADERS])
        writer = SheetsBatchWriter(
            SimpleNamespace(
                google_sheet_id="test",
                sheets_batch_size=10,
                sheets_min_write_interval=0,
            ),
            _RepositoryFake(),
        )

        writer._apply_fixed_layout(worksheet)

        column_requests = [
            request
            for request in worksheet.spreadsheet.requests
            if request.get("updateDimensionProperties", {})
            .get("range", {})
            .get("dimension") == "COLUMNS"
        ]
        self.assertEqual(len(column_requests), len(COLUMN_WIDTHS))


if __name__ == "__main__":
    unittest.main()
