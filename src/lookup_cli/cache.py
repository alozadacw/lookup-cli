"""
SQLite cache keyed by (plugin_name, identifier), with per-entry TTL.

Deliberately per-plugin, not per-identifier-only: a stale Jamf result
and a fresh Okta result for the same person can coexist, so a slow or
down service never forces a full re-fetch of everything else.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lookup_cli.plugins.base import ConnectorResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    plugin_name TEXT NOT NULL,
    identifier TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (plugin_name, identifier)
);
"""


class Cache:
    def __init__(self, db_path: str | Path, default_ttl: timedelta = timedelta(hours=1)):
        self.db_path = str(db_path)
        self.default_ttl = default_ttl
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def put(self, result: ConnectorResult) -> None:
        payload = asdict(result)
        payload["fetched_at"] = result.fetched_at.isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries (plugin_name, identifier, payload, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(plugin_name, identifier) DO UPDATE SET
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at
                """,
                (result.plugin_name, result.identifier, json.dumps(payload), payload["fetched_at"]),
            )

    def get(
        self,
        plugin_name: str,
        identifier: str,
        ttl: timedelta | None = None,
    ) -> ConnectorResult | None:
        """Return the cached result if present and not expired, else None."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM cache_entries WHERE plugin_name = ? AND identifier = ?",
                (plugin_name, identifier),
            ).fetchone()

        if row is None:
            return None

        payload_raw, fetched_at_raw = row
        fetched_at = datetime.fromisoformat(fetched_at_raw)
        if datetime.now(timezone.utc) - fetched_at > effective_ttl:
            return None

        payload = json.loads(payload_raw)
        payload["fetched_at"] = fetched_at
        return ConnectorResult(**payload)

    def invalidate(self, plugin_name: str, identifier: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM cache_entries WHERE plugin_name = ? AND identifier = ?",
                (plugin_name, identifier),
            )
