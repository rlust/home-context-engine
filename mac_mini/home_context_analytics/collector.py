"""Offline collector for normalized, whitelisted JSONL transition records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .model import Episode, Feedback, ValidationError, parse_record
from .store import LocalStore


def collect_jsonl(
    stream: TextIO,
    database: Path,
    *,
    retention_days: int = 45,
    drift_window_days: int = 14,
    as_of: datetime | None = None,
) -> dict[str, int]:
    """Validate and ingest transition records from a local stream.

    This function has no HA client and no network path. The only mutation is the
    caller-selected local SQLite database.
    """

    counts = {"episodes_inserted": 0, "feedback_inserted": 0, "duplicates": 0, "purged": 0}
    reference_time = as_of or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        raise ValidationError("as_of must include a timezone")
    _validate_retention(retention_days, drift_window_days)
    with LocalStore(database) as store:
        try:
            store.set_retention_policy(retention_days, drift_window_days)
            for line_number, raw_line in enumerate(stream, start=1):
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line)
                    record = parse_record(payload)
                    inserted = (
                        store.add_episode(record)
                        if isinstance(record, Episode)
                        else store.add_feedback(record)
                    )
                except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                    raise ValidationError(f"line {line_number}: {exc}") from exc
                if inserted:
                    key = "episodes_inserted" if isinstance(record, Episode) else "feedback_inserted"
                    counts[key] += 1
                else:
                    counts["duplicates"] += 1
            counts["purged"] = store.purge(retention_days, reference_time)
            store.commit()
        except Exception:
            store.connection.rollback()
            raise
    return counts


def _validate_retention(retention_days: int, drift_window_days: int) -> None:
    if drift_window_days < 1:
        raise ValidationError("drift_window_days must be at least 1")
    if retention_days <= 2 * drift_window_days:
        raise ValidationError("retention_days must be greater than twice drift_window_days")


def collect_continuous_file(
    input_path: Path,
    database: Path,
    *,
    retention_days: int = 45,
    drift_window_days: int = 14,
    max_quarantine_distinct: int = 1000,
    as_of: datetime | None = None,
) -> dict[str, int]:
    """Ingest only newly appended lines, isolating and deduplicating failures."""

    reference_time = as_of or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        raise ValidationError("as_of must include a timezone")
    _validate_retention(retention_days, drift_window_days)
    resolved = input_path.resolve(strict=True)
    source_id = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()
    stat = resolved.stat()
    counts = {
        "episodes_inserted": 0,
        "feedback_inserted": 0,
        "duplicates": 0,
        "rejected_records": 0,
        "quarantined_distinct": 0,
        "quarantine_pruned": 0,
        "purged": 0,
    }
    seen_at = reference_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    with LocalStore(database) as store:
        store.set_retention_policy(retention_days, drift_window_days)
        checkpoint = store.get_checkpoint(source_id)
        offset = 0
        if checkpoint is not None:
            same_file = checkpoint["device"] == stat.st_dev and checkpoint["inode"] == stat.st_ino
            if same_file and stat.st_size >= checkpoint["byte_offset"]:
                offset = checkpoint["byte_offset"]
        with resolved.open("rb") as stream:
            stream.seek(offset)
            line_number = 0
            while True:
                byte_offset = stream.tell()
                raw_line = stream.readline()
                if not raw_line:
                    break
                if not raw_line.endswith(b"\n"):
                    break
                line_number += 1
                next_offset = stream.tell()
                if not raw_line.strip():
                    store.set_checkpoint(
                        source_id, device=stat.st_dev, inode=stat.st_ino,
                        byte_offset=next_offset, updated_at=seen_at
                    )
                    store.commit()
                    continue
                try:
                    payload = json.loads(raw_line.decode("utf-8"))
                    record = parse_record(payload)
                    inserted = (
                        store.add_episode(record)
                        if isinstance(record, Episode)
                        else store.add_feedback(record)
                    )
                    if inserted:
                        key = "episodes_inserted" if isinstance(record, Episode) else "feedback_inserted"
                        counts[key] += 1
                    else:
                        counts["duplicates"] += 1
                except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                    store.connection.rollback()
                    fingerprint = hashlib.sha256(raw_line).hexdigest()
                    is_new = store.record_rejection(
                        source_id=source_id,
                        fingerprint=fingerprint,
                        line_number=line_number,
                        byte_offset=byte_offset,
                        error=type(exc).__name__,
                        seen_at=seen_at,
                    )
                    counts["rejected_records"] += 1
                    counts["quarantined_distinct"] += int(is_new)
                store.set_checkpoint(
                    source_id, device=stat.st_dev, inode=stat.st_ino,
                    byte_offset=next_offset, updated_at=seen_at
                )
                store.commit()
        counts["purged"] = store.purge(retention_days, reference_time)
        counts["quarantine_pruned"] = store.prune_rejections(max_quarantine_distinct)
        store.commit()
    return counts
