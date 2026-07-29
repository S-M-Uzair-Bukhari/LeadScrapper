"""SQLite-backed lead checkpoints and upload state."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from ..pipeline.processor import ProcessedLead


class SQLiteLeadRepository:
    """Persist qualified leads as they pass through the pipeline."""

    def __init__(self, path: str, run_id: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._lock = Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                platform_worker TEXT NOT NULL,
                keyword TEXT NOT NULL,
                dedup_key TEXT NOT NULL,
                lead_json TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                uploaded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, dedup_key)
            )
            """
        )
        self._connection.commit()

    def save(
        self,
        platform_worker: str,
        keyword: str,
        item: ProcessedLead,
        dedup_key: str,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO processed_leads (
                    run_id, platform_worker, keyword, dedup_key,
                    lead_json, analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    platform_worker,
                    keyword,
                    dedup_key,
                    json.dumps(item.lead.model_dump(), default=str),
                    json.dumps(asdict(item.analysis), default=str),
                ),
            )
            self._connection.commit()

    def mark_uploaded(self, dedup_keys: list[str]) -> None:
        if not dedup_keys:
            return
        placeholders = ",".join("?" for _ in dedup_keys)
        with self._lock:
            self._connection.execute(
                f"""
                UPDATE processed_leads
                SET uploaded = 1
                WHERE run_id = ? AND dedup_key IN ({placeholders})
                """,
                [self.run_id, *dedup_keys],
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()
