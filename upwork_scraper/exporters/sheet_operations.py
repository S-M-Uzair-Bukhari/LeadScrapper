"""Low-level Sheets requests shared by both upload paths."""

from __future__ import annotations

from typing import Sequence


def prepend_rows_requests(
    sheet_id: int,
    rows: Sequence[Sequence[object]],
    start_row_index: int = 1,
) -> list[dict]:
    """Build one batchUpdate that inserts and fills rows below the header."""
    if not rows:
        return []

    row_data = []
    for row in rows:
        cells = []
        for value in row:
            if isinstance(value, bool):
                user_value = {"boolValue": value}
            elif isinstance(value, (int, float)):
                user_value = {"numberValue": value}
            else:
                user_value = {
                    "stringValue": "" if value is None else str(value)
                }
            cells.append({"userEnteredValue": user_value})
        row_data.append({"values": cells})

    return [
        {
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_row_index,
                    "endIndex": start_row_index + len(rows),
                },
                "inheritFromBefore": False,
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row_index,
                    "endRowIndex": start_row_index + len(rows),
                    "startColumnIndex": 0,
                },
                "rows": row_data,
                "fields": "userEnteredValue",
            }
        },
    ]
