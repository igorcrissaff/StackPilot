from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import normalize_base_domain

GLOBAL_SCOPE = "global"
BASE_DOMAIN_KEY = "base_domain"


class SettingsService:
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    scope TEXT NOT NULL,
                    key   TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (scope, key)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, scope: str, key: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        finally:
            conn.close()
        return None if row is None else str(row["value"])

    def set(self, scope: str, key: str, value: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO app_settings (scope, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(scope, key) DO UPDATE SET value=excluded.value",
                (scope, key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, scope: str, key: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM app_settings WHERE scope = ? AND key = ?",
                (scope, key),
            )
            conn.commit()
        finally:
            conn.close()

    def all(self, scope: str) -> dict[str, str]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT key, value FROM app_settings WHERE scope = ?",
                (scope,),
            ).fetchall()
        finally:
            conn.close()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def get_base_domain(self, default: str) -> str:
        return self.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) or default

    def set_base_domain(self, value: str) -> str:
        normalized = normalize_base_domain(value)
        self.set(GLOBAL_SCOPE, BASE_DOMAIN_KEY, normalized)
        return normalized

    def reset_base_domain(self) -> None:
        self.delete(GLOBAL_SCOPE, BASE_DOMAIN_KEY)
