from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from src.storage.models import CheckResult, OverrideDecision


class Repository:
    def __init__(self, db_path: str = "workdash.db") -> None:
        self.path = Path(db_path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS check_results (
                result_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS overrides (
                override_id TEXT PRIMARY KEY,
                result_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def upsert_results(self, results: Iterable[CheckResult]) -> None:
        with self.conn:
            for result in results:
                payload = result.model_dump_json()
                self.conn.execute(
                    "INSERT OR REPLACE INTO check_results(result_id, payload) VALUES (?, ?)",
                    (result.result_id, payload),
                )
                self._audit("check_result_upsert", json.loads(payload))

    def list_results(self) -> list[CheckResult]:
        rows = self.conn.execute("SELECT payload FROM check_results ORDER BY result_id").fetchall()
        return [CheckResult.model_validate_json(row["payload"]) for row in rows]

    def add_override(self, decision: OverrideDecision) -> None:
        payload = decision.model_dump_json()
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO overrides(override_id, result_id, payload) VALUES (?, ?, ?)",
                (decision.override_id, decision.result_id, payload),
            )
            self._audit("override_added", json.loads(payload))

    def list_overrides(self) -> list[OverrideDecision]:
        rows = self.conn.execute("SELECT payload FROM overrides ORDER BY override_id").fetchall()
        return [OverrideDecision.model_validate_json(row["payload"]) for row in rows]

    def export_audit(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def _audit(self, event_type: str, event_payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO audit_log(event_type, event_payload) VALUES (?, ?)",
            (event_type, json.dumps(event_payload, default=str)),
        )
