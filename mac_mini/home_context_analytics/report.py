"""Deterministic aggregate reporting for Hermes and human review."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .store import read_only_connection


def _accuracy(correct: int, incorrect: int) -> float | None:
    scored = correct + incorrect
    return round(correct / scored, 4) if scored else None


def _window_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    outcomes = Counter(row["outcome"] for row in materialized if row["outcome"] is not None)
    signal_issue_count = sum(row["has_signal_issue"] for row in materialized)
    return {
        "episodes": len(materialized),
        "reviewed": sum(outcomes.values()),
        "confirmed": outcomes["confirm"],
        "wrong": outcomes["wrong"],
        "unsure": outcomes["unsure"],
        "accuracy": _accuracy(outcomes["confirm"], outcomes["wrong"]),
        "signal_issue_rate": round(signal_issue_count / len(materialized), 4) if materialized else None,
    }


def build_report(database: Path, *, as_of: datetime, window_days: int = 14) -> dict[str, Any]:
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    as_of_utc = as_of.astimezone(timezone.utc)
    with read_only_connection(database) as connection:
        records = []
        for row in connection.execute(
            """
            SELECT e.episode_id, e.occurred_at, e.activity, e.confidence, e.signals_json,
                   f.occurred_at AS feedback_occurred_at, f.outcome, f.corrected_activity
            FROM episodes e
            LEFT JOIN feedback f ON f.episode_id = e.episode_id
            ORDER BY e.occurred_at, e.episode_id
            """
        ):
            signals = json.loads(row["signals_json"])
            episode_time = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
            feedback_time = (
                datetime.fromisoformat(row["feedback_occurred_at"].replace("Z", "+00:00"))
                if row["feedback_occurred_at"]
                else None
            )
            feedback_is_visible = feedback_time is not None and feedback_time <= as_of_utc
            records.append(
                {
                    "episode_id": row["episode_id"],
                    "occurred_at": episode_time,
                    "activity": row["activity"],
                    "confidence": row["confidence"],
                    "outcome": row["outcome"] if feedback_is_visible else None,
                    "corrected_activity": row["corrected_activity"] if feedback_is_visible else None,
                    "has_signal_issue": int(any(state in {"stale", "missing"} for state in signals.values())),
                    "signal_states": signals,
                }
            )

    records = [row for row in records if row["occurred_at"] <= as_of_utc]

    outcome_counts = Counter(row["outcome"] for row in records if row["outcome"] is not None)
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    confidence: dict[str, Counter[str]] = defaultdict(Counter)
    for row in records:
        outcome = row["outcome"]
        if outcome in {"confirm", "wrong"}:
            actual = row["activity"] if outcome == "confirm" else row["corrected_activity"]
            confusion[row["activity"]][actual] += 1
            bucket_start = (row["confidence"] // 10) * 10
            bucket = "100" if bucket_start == 100 else f"{bucket_start:02d}-{bucket_start + 9:02d}"
            confidence[bucket]["reviewed"] += 1
            confidence[bucket]["correct" if outcome == "confirm" else "wrong"] += 1

    confidence_buckets = {}
    for bucket in sorted(confidence):
        bucket_counts = confidence[bucket]
        confidence_buckets[bucket] = {
            "reviewed": bucket_counts["reviewed"],
            "correct": bucket_counts["correct"],
            "wrong": bucket_counts["wrong"],
            "observed_accuracy": _accuracy(bucket_counts["correct"], bucket_counts["wrong"]),
        }

    signal_states = Counter(
        state for row in records for state in row["signal_states"].values()
    )
    episodes_with_signal_issues = sum(row["has_signal_issue"] for row in records)
    episodes_with_missing = sum(
        any(state == "missing" for state in row["signal_states"].values()) for row in records
    )
    episodes_with_stale = sum(
        any(state == "stale" for state in row["signal_states"].values()) for row in records
    )

    current_start = as_of_utc - timedelta(days=window_days)
    previous_start = current_start - timedelta(days=window_days)
    current_rows = [row for row in records if current_start <= row["occurred_at"] <= as_of_utc]
    previous_rows = [row for row in records if previous_start <= row["occurred_at"] < current_start]
    current = _window_summary(current_rows)
    previous = _window_summary(previous_rows)
    accuracy_delta = None
    if current["accuracy"] is not None and previous["accuracy"] is not None:
        accuracy_delta = round(current["accuracy"] - previous["accuracy"], 4)
    signal_delta = None
    if current["signal_issue_rate"] is not None and previous["signal_issue_rate"] is not None:
        signal_delta = round(current["signal_issue_rate"] - previous["signal_issue_rate"], 4)

    return {
        "schema_version": 1,
        "as_of": as_of_utc.isoformat().replace("+00:00", "Z"),
        "scope": "Newark Home Context local anonymous aggregates",
        "episodes": len(records),
        "reviewed_denominator": sum(outcome_counts.values()),
        "unreviewed": len(records) - sum(outcome_counts.values()),
        "feedback": {
            "confirmed": outcome_counts["confirm"],
            "wrong": outcome_counts["wrong"],
            "unsure": outcome_counts["unsure"],
            "scored_accuracy": _accuracy(outcome_counts["confirm"], outcome_counts["wrong"]),
        },
        "per_activity_confusion": {
            predicted: dict(sorted(actual_counts.items()))
            for predicted, actual_counts in sorted(confusion.items())
        },
        "confidence_buckets": confidence_buckets,
        "signal_health": {
            "episodes_with_stale_or_missing": episodes_with_signal_issues,
            "episode_issue_rate": round(episodes_with_signal_issues / len(records), 4) if records else None,
            "episodes_with_missing": episodes_with_missing,
            "missing_episode_rate": round(episodes_with_missing / len(records), 4) if records else None,
            "episodes_with_stale": episodes_with_stale,
            "stale_episode_rate": round(episodes_with_stale / len(records), 4) if records else None,
            "state_counts": dict(sorted(signal_states.items())),
        },
        "window_comparison": {
            "window_days": window_days,
            "minimum_reviewed_per_window": 20,
            "previous": previous,
            "current": current,
            "accuracy_delta": accuracy_delta,
            "signal_issue_rate_delta": signal_delta,
            "comparison_available": previous["reviewed"] > 0 and current["reviewed"] > 0,
            "drift_ready": previous["reviewed"] >= 20 and current["reviewed"] >= 20,
        },
        "privacy": {
            "raw_person_identity": False,
            "camera_audio_messages_gps": False,
            "network_used": False,
        },
    }


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def report_markdown(report: dict[str, Any]) -> str:
    feedback = report["feedback"]
    signal = report["signal_health"]
    lines = [
        "# Newark Home Context Local Report",
        "",
        f"As of: `{report['as_of']}`",
        "",
        "## Review coverage",
        "",
        f"- Episodes: {report['episodes']}",
        f"- Reviewed denominator: {report['reviewed_denominator']}",
        f"- Unreviewed: {report['unreviewed']}",
        f"- Confirmed / Wrong / Unsure: {feedback['confirmed']} / {feedback['wrong']} / {feedback['unsure']}",
        f"- Scored accuracy (Unsure excluded): {feedback['scored_accuracy']}",
        "",
        "## Signal health",
        "",
        f"- Episodes with stale or missing input: {signal['episodes_with_stale_or_missing']}",
        f"- Episode issue rate: {signal['episode_issue_rate']}",
        f"- Missing-input episode rate: {signal['missing_episode_rate']}",
        f"- Stale-input episode rate: {signal['stale_episode_rate']}",
        "",
        "## Per-activity confusion (predicted -> actual)",
        "",
    ]
    confusion = report["per_activity_confusion"]
    if confusion:
        for predicted, actual in confusion.items():
            rendered = ", ".join(f"{name}: {count}" for name, count in actual.items())
            lines.append(f"- {predicted} -> {rendered}")
    else:
        lines.append("- No scored feedback yet.")
    lines.extend(["", "## Confidence buckets", ""])
    if report["confidence_buckets"]:
        lines.extend(["| Score | Reviewed | Correct | Wrong | Observed accuracy |", "|---|---:|---:|---:|---:|"])
        for bucket, values in report["confidence_buckets"].items():
            lines.append(
                f"| {bucket} | {values['reviewed']} | {values['correct']} | {values['wrong']} | {values['observed_accuracy']} |"
            )
    else:
        lines.append("No scored feedback yet.")
    window = report["window_comparison"]
    lines.extend(
        [
            "",
            f"## Drift-ready {window['window_days']}-day windows",
            "",
            f"- Previous: {json.dumps(window['previous'], sort_keys=True)}",
            f"- Current: {json.dumps(window['current'], sort_keys=True)}",
            f"- Accuracy delta: {window['accuracy_delta']}",
            f"- Signal issue-rate delta: {window['signal_issue_rate_delta']}",
            f"- Comparison available: {window['comparison_available']}",
            f"- Minimum reviewed per window: {window['minimum_reviewed_per_window']}",
            f"- Drift-ready: {window['drift_ready']}",
            "",
            "Hermes input is limited to this aggregate report; raw episodes remain local.",
            "",
        ]
    )
    return "\n".join(lines)
