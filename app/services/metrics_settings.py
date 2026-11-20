from __future__ import annotations

import sqlite3
from pathlib import Path

MIN_REFRESH_SECONDS = 5
MAX_REFRESH_SECONDS = 900
DEFAULT_REFRESH_SECONDS = 10
_REFRESH_KEY = "metrics_refresh_interval_seconds"


class MetricsSettingsStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_refresh_interval(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (_REFRESH_KEY,)
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return DEFAULT_REFRESH_SECONDS

        try:
            value = int(row["value"])
        except (TypeError, ValueError):
            return DEFAULT_REFRESH_SECONDS

        if not MIN_REFRESH_SECONDS <= value <= MAX_REFRESH_SECONDS:
            return DEFAULT_REFRESH_SECONDS
        return value

    def set_refresh_interval(self, seconds: int) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError("interval must be an integer")
        if not MIN_REFRESH_SECONDS <= seconds <= MAX_REFRESH_SECONDS:
            raise ValueError(
                f"interval must be between {MIN_REFRESH_SECONDS} and {MAX_REFRESH_SECONDS}"
            )

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (_REFRESH_KEY, str(seconds)),
            )
            conn.commit()
        finally:
            conn.close()
