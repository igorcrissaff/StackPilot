from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel


class UsedImage(BaseModel):
    image: str
    last_used_at: int
    use_count: int
    stack_name: str | None = None


class HubCache:
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
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tag_cache (
                    repo TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS used_images (
                    image TEXT PRIMARY KEY,
                    last_used_at INTEGER NOT NULL,
                    use_count INTEGER NOT NULL,
                    stack_name TEXT
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_search(self, query: str, ttl_seconds: int) -> tuple[str | None, int | None, bool]:
        return self._get_cached("search_cache", "query", query, ttl_seconds)

    def set_search(self, query: str, payload: str) -> None:
        self._set_cached("search_cache", "query", query, payload)

    def get_tags(self, repo: str, ttl_seconds: int) -> tuple[str | None, int | None, bool]:
        return self._get_cached("tag_cache", "repo", repo, ttl_seconds)

    def set_tags(self, repo: str, payload: str) -> None:
        self._set_cached("tag_cache", "repo", repo, payload)

    def _get_cached(
        self, table: str, key_column: str, key: str, ttl_seconds: int
    ) -> tuple[str | None, int | None, bool]:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT payload, fetched_at FROM {table} WHERE {key_column} = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None, None, False

        fetched_at = int(row["fetched_at"])
        is_stale = int(time.time()) - fetched_at > ttl_seconds
        return str(row["payload"]), fetched_at, is_stale

    def _set_cached(self, table: str, key_column: str, key: str, payload: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT INTO {table} ({key_column}, payload, fetched_at) VALUES (?, ?, ?) "
                f"ON CONFLICT({key_column}) DO UPDATE SET "
                "payload=excluded.payload, fetched_at=excluded.fetched_at",
                (key, payload, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()

    def record_used_image(self, image: str, stack_name: str | None = None) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO used_images (image, last_used_at, use_count, stack_name)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(image) DO UPDATE SET
                    last_used_at=excluded.last_used_at,
                    use_count=used_images.use_count+1,
                    stack_name=excluded.stack_name
                """,
                (image, int(time.time()), stack_name),
            )
            conn.commit()
        finally:
            conn.close()

    def list_used_images(self, limit: int = 50) -> list[UsedImage]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT image, last_used_at, use_count, stack_name FROM used_images "
                "ORDER BY last_used_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        return [
            UsedImage(
                image=row["image"],
                last_used_at=int(row["last_used_at"]),
                use_count=int(row["use_count"]),
                stack_name=row["stack_name"],
            )
            for row in rows
        ]
