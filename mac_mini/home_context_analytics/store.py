"""SQLite storage with bounded retention and read-only reporting access."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .model import Episode, Feedback


SCHEMA_VERSION = "1"


def _open_writable(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS episodes (
            episode_id TEXT PRIMARY KEY,
            source_event_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL,
            mode TEXT NOT NULL,
            activity TEXT NOT NULL,
            confidence INTEGER NOT NULL CHECK(confidence BETWEEN 0 AND 100),
            active_rooms_json TEXT NOT NULL,
            resident_bucket TEXT NOT NULL,
            signals_json TEXT NOT NULL,
            observer_version TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feedback (
            episode_id TEXT PRIMARY KEY REFERENCES episodes(episode_id) ON DELETE CASCADE,
            source_event_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('confirm', 'wrong', 'unsure')),
            corrected_activity TEXT
        );
        CREATE INDEX IF NOT EXISTS episodes_occurred_at_idx ON episodes(occurred_at);
        CREATE INDEX IF NOT EXISTS feedback_occurred_at_idx ON feedback(occurred_at);
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    version = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()[0]
    if version != SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(f"unsupported database schema version: {version}")
    connection.commit()
    os.chmod(path, 0o600)
    return connection


@contextmanager
def read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_file():
        raise FileNotFoundError(f"analytics database does not exist: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


class LocalStore:
    def __init__(self, path: Path):
        self.path = path
        self.connection = _open_writable(path)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LocalStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def add_episode(self, episode: Episode) -> bool:
        values = (
            episode.episode_id,
            episode.source_event_id,
            episode.occurred_at,
            episode.mode,
            episode.activity,
            episode.confidence,
            json.dumps(episode.active_rooms, separators=(",", ":")),
            episode.resident_bucket,
            json.dumps(dict(episode.signals), sort_keys=True, separators=(",", ":")),
            episode.observer_version,
        )
        try:
            self.connection.execute(
                """
                INSERT INTO episodes(
                    episode_id, source_event_id, occurred_at, mode, activity, confidence,
                    active_rooms_json, resident_bucket, signals_json, observer_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return True
        except sqlite3.IntegrityError as exc:
            existing = self.connection.execute(
                """
                SELECT episode_id, source_event_id, occurred_at, mode, activity, confidence,
                       active_rooms_json, resident_bucket, signals_json, observer_version
                FROM episodes WHERE episode_id = ? OR source_event_id = ?
                """,
                (episode.episode_id, episode.source_event_id),
            ).fetchone()
            if existing is not None and tuple(existing) == values:
                return False
            raise ValueError("episode/source event identifier collision") from exc

    def add_feedback(self, feedback: Feedback) -> bool:
        episode_row = self.connection.execute(
            "SELECT occurred_at FROM episodes WHERE episode_id = ?", (feedback.episode_id,)
        ).fetchone()
        if episode_row is None:
            raise ValueError("feedback must reference an existing episode")
        episode_time = datetime.fromisoformat(episode_row[0].replace("Z", "+00:00"))
        feedback_time = datetime.fromisoformat(feedback.occurred_at.replace("Z", "+00:00"))
        if feedback_time < episode_time:
            raise ValueError("feedback cannot occur before its prediction episode")
        values = (
            feedback.episode_id,
            feedback.source_event_id,
            feedback.occurred_at,
            feedback.outcome,
            feedback.corrected_activity,
        )
        try:
            self.connection.execute(
                """
                INSERT INTO feedback(
                    episode_id, source_event_id, occurred_at, outcome, corrected_activity
                ) VALUES (?, ?, ?, ?, ?)
                """,
                values,
            )
            return True
        except sqlite3.IntegrityError as exc:
            existing = self.connection.execute(
                """
                SELECT episode_id, source_event_id, occurred_at, outcome, corrected_activity
                FROM feedback WHERE episode_id = ? OR source_event_id = ?
                """,
                (feedback.episode_id, feedback.source_event_id),
            ).fetchone()
            if existing is not None and tuple(existing) == values:
                return False
            raise ValueError("feedback must reference an existing episode and use unique identifiers") from exc

    def purge(self, retention_days: int, as_of: datetime) -> int:
        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        if as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        cutoff = (as_of.astimezone(timezone.utc) - timedelta(days=retention_days)).isoformat().replace(
            "+00:00", "Z"
        )
        cursor = self.connection.execute(
            "DELETE FROM episodes WHERE julianday(occurred_at) < julianday(?)", (cutoff,)
        )
        return cursor.rowcount

    def commit(self) -> None:
        self.connection.commit()
