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


SCHEMA_VERSION = "3"


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
            observer_version TEXT NOT NULL,
            context_flags_json TEXT NOT NULL DEFAULT '[]',
            next_activity TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback_events (
            source_event_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
            occurred_at TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('confirm', 'wrong', 'unsure')),
            corrected_activity TEXT
        );
        CREATE TABLE IF NOT EXISTS ingest_checkpoints (
            source_id TEXT PRIMARY KEY,
            device INTEGER NOT NULL,
            inode INTEGER NOT NULL,
            byte_offset INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rejected_records (
            source_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            first_line_number INTEGER NOT NULL,
            first_byte_offset INTEGER NOT NULL,
            error TEXT NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY(source_id, fingerprint)
        );
        CREATE INDEX IF NOT EXISTS episodes_occurred_at_idx ON episodes(occurred_at);
        CREATE INDEX IF NOT EXISTS feedback_events_episode_idx
            ON feedback_events(episode_id, occurred_at, source_event_id);
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    version = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()[0]
    if version == "1":
        legacy_feedback = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'feedback'"
        ).fetchone()
        if legacy_feedback:
            connection.execute(
                """
                INSERT OR IGNORE INTO feedback_events(
                    source_event_id, episode_id, occurred_at, outcome, corrected_activity
                )
                SELECT source_event_id, episode_id, occurred_at, outcome, corrected_activity
                FROM feedback
                """
            )
            connection.execute("DROP TABLE feedback")
        connection.execute("UPDATE metadata SET value = '2' WHERE key = 'schema_version'")
        version = "2"
    if version == "2":
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(episodes)").fetchall()
        }
        if "context_flags_json" not in columns:
            connection.execute(
                "ALTER TABLE episodes ADD COLUMN context_flags_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "next_activity" not in columns:
            connection.execute("ALTER TABLE episodes ADD COLUMN next_activity TEXT")
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION,)
        )
        version = SCHEMA_VERSION
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
            json.dumps(episode.context_flags, separators=(",", ":")),
            episode.next_activity,
        )
        try:
            self.connection.execute(
                """
                INSERT INTO episodes(
                    episode_id, source_event_id, occurred_at, mode, activity, confidence,
                    active_rooms_json, resident_bucket, signals_json, observer_version,
                    context_flags_json, next_activity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return True
        except sqlite3.IntegrityError as exc:
            existing = self.connection.execute(
                """
                SELECT episode_id, source_event_id, occurred_at, mode, activity, confidence,
                       active_rooms_json, resident_bucket, signals_json, observer_version,
                       context_flags_json, next_activity
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
                INSERT INTO feedback_events(
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
                FROM feedback_events WHERE source_event_id = ?
                """,
                (feedback.source_event_id,),
            ).fetchone()
            if existing is not None and tuple(existing) == values:
                return False
            raise ValueError("feedback source event identifier collision") from exc

    def get_checkpoint(self, source_id: str) -> sqlite3.Row | None:
        self.connection.row_factory = sqlite3.Row
        return self.connection.execute(
            "SELECT device, inode, byte_offset FROM ingest_checkpoints WHERE source_id = ?",
            (source_id,),
        ).fetchone()

    def set_checkpoint(
        self, source_id: str, *, device: int, inode: int, byte_offset: int, updated_at: str
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO ingest_checkpoints(source_id, device, inode, byte_offset, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                device = excluded.device,
                inode = excluded.inode,
                byte_offset = excluded.byte_offset,
                updated_at = excluded.updated_at
            """,
            (source_id, device, inode, byte_offset, updated_at),
        )

    def record_rejection(
        self,
        *,
        source_id: str,
        fingerprint: str,
        line_number: int,
        byte_offset: int,
        error: str,
        seen_at: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT INTO rejected_records(
                source_id, fingerprint, first_line_number, first_byte_offset,
                error, occurrences, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(source_id, fingerprint) DO UPDATE SET
                occurrences = rejected_records.occurrences + 1,
                last_seen_at = excluded.last_seen_at
            """,
            (source_id, fingerprint, line_number, byte_offset, error[:500], seen_at),
        )
        return cursor.rowcount == 1 and self.connection.execute(
            "SELECT occurrences FROM rejected_records WHERE source_id = ? AND fingerprint = ?",
            (source_id, fingerprint),
        ).fetchone()[0] == 1

    def set_retention_policy(self, retention_days: int, drift_window_days: int) -> None:
        self.connection.executemany(
            """
            INSERT INTO metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (
                ("retention_days", str(retention_days)),
                ("drift_window_days", str(drift_window_days)),
            ),
        )

    def prune_rejections(self, max_distinct: int) -> int:
        if max_distinct < 1:
            raise ValueError("max_distinct quarantine records must be at least 1")
        overflow = self.connection.execute(
            "SELECT MAX(COUNT(*) - ?, 0) FROM rejected_records", (max_distinct,)
        ).fetchone()[0]
        if not overflow:
            return 0
        rows = self.connection.execute(
            """
            SELECT source_id, fingerprint, occurrences
            FROM rejected_records
            ORDER BY julianday(last_seen_at), source_id, fingerprint
            LIMIT ?
            """,
            (overflow,),
        ).fetchall()
        pruned_occurrences = sum(row[2] for row in rows)
        self.connection.executemany(
            "DELETE FROM rejected_records WHERE source_id = ? AND fingerprint = ?",
            ((row[0], row[1]) for row in rows),
        )
        for key, amount in (
            ("rejected_pruned_distinct", len(rows)),
            ("rejected_pruned_occurrences", pruned_occurrences),
        ):
            self.connection.execute(
                """
                INSERT INTO metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = CAST(CAST(metadata.value AS INTEGER) + CAST(excluded.value AS INTEGER) AS TEXT)
                """,
                (key, str(amount)),
            )
        return len(rows)

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
