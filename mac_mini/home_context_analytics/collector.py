"""Offline collector for normalized, whitelisted JSONL transition records."""

from __future__ import annotations

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
    retention_days: int = 30,
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
    with LocalStore(database) as store:
        try:
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
