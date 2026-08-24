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
    scored = Counter(
        row["outcome"]
        for row in materialized
        if row["audit_consistent"] and row["outcome"] in {"confirm", "wrong"}
    )
    signal_issue_count = sum(row["has_signal_issue"] for row in materialized)
    return {
        "episodes": len(materialized),
        "reviewed": sum(outcomes.values()),
        "confirmed": outcomes["confirm"],
        "wrong": outcomes["wrong"],
        "unsure": outcomes["unsure"],
        "accuracy": _accuracy(scored["confirm"], scored["wrong"]),
        "signal_issue_rate": round(signal_issue_count / len(materialized), 4) if materialized else None,
    }


def build_report(database: Path, *, as_of: datetime, window_days: int = 14) -> dict[str, Any]:
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    as_of_utc = as_of.astimezone(timezone.utc)
    with read_only_connection(database) as connection:
        schema_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        retention_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'retention_days'"
        ).fetchone()
        retention_days = int(retention_row["value"]) if retention_row else None
        if retention_days is not None and retention_days <= 2 * window_days:
            raise ValueError("report window violates retention > 2 x drift-window policy")
        records = []
        for row in connection.execute(
            """
            SELECT episode_id, occurred_at, activity, confidence, signals_json
            FROM episodes
            ORDER BY occurred_at, episode_id
            """
        ):
            signals = json.loads(row["signals_json"])
            episode_time = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
            records.append(
                {
                    "episode_id": row["episode_id"],
                    "occurred_at": episode_time,
                    "activity": row["activity"],
                    "confidence": row["confidence"],
                    "outcome": None,
                    "corrected_activity": None,
                    "audit_consistent": True,
                    "audit_issues": [],
                    "has_signal_issue": int(any(state in {"stale", "missing"} for state in signals.values())),
                    "signal_states": signals,
                }
            )

        latest_feedback: dict[str, Any] = {}
        as_of_text = as_of_utc.isoformat().replace("+00:00", "Z")
        for row in connection.execute(
            """
            SELECT source_event_id, episode_id, occurred_at, outcome, corrected_activity,
                   audit_consistent, audit_issues_json
            FROM feedback_events
            WHERE julianday(occurred_at) <= julianday(?)
            ORDER BY episode_id, julianday(occurred_at), source_event_id
            """,
            (as_of_text,),
        ):
            latest_feedback[row["episode_id"]] = row
        rejected = connection.execute(
            "SELECT COUNT(*) AS distinct_count, COALESCE(SUM(occurrences), 0) AS occurrences FROM rejected_records"
        ).fetchone()
        pruned_values = {
            row["key"]: int(row["value"])
            for row in connection.execute(
                "SELECT key, value FROM metadata WHERE key IN ('rejected_pruned_distinct', 'rejected_pruned_occurrences')"
            )
        }

    records = [row for row in records if row["occurred_at"] <= as_of_utc]
    for row in records:
        feedback = latest_feedback.get(row["episode_id"])
        if feedback:
            row["outcome"] = feedback["outcome"]
            row["corrected_activity"] = feedback["corrected_activity"]
            row["audit_consistent"] = bool(feedback["audit_consistent"])
            row["audit_issues"] = json.loads(feedback["audit_issues_json"])

    outcome_counts = Counter(row["outcome"] for row in records if row["outcome"] is not None)
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    confidence: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"reviewed": 0, "correct": 0, "wrong": 0, "confidence_sum": 0}
    )
    for row in records:
        outcome = row["outcome"]
        if row["audit_consistent"] and outcome in {"confirm", "wrong"}:
            actual = row["activity"] if outcome == "confirm" else row["corrected_activity"]
            confusion[row["activity"]][actual] += 1
            bucket_start = (row["confidence"] // 10) * 10
            bucket = "100" if bucket_start == 100 else f"{bucket_start:02d}-{bucket_start + 9:02d}"
            confidence[bucket]["reviewed"] += 1
            confidence[bucket]["correct" if outcome == "confirm" else "wrong"] += 1
            confidence[bucket]["confidence_sum"] += row["confidence"]

    confidence_buckets = {}
    for bucket in sorted(confidence):
        bucket_counts = confidence[bucket]
        mean_predicted = round(bucket_counts["confidence_sum"] / bucket_counts["reviewed"] / 100, 4)
        observed_accuracy = _accuracy(bucket_counts["correct"], bucket_counts["wrong"])
        confidence_buckets[bucket] = {
            "reviewed": bucket_counts["reviewed"],
            "correct": bucket_counts["correct"],
            "wrong": bucket_counts["wrong"],
            "mean_predicted_confidence": mean_predicted,
            "observed_accuracy": observed_accuracy,
            "absolute_calibration_gap": round(abs(mean_predicted - observed_accuracy), 4),
        }
    scored_count = sum(bucket["reviewed"] for bucket in confidence_buckets.values())
    ece = (
        round(
            sum(
                bucket["reviewed"] * bucket["absolute_calibration_gap"]
                for bucket in confidence_buckets.values()
            ) / scored_count,
            4,
        )
        if scored_count
        else None
    )

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
    audit_issue_counts = Counter(
        issue for row in records for issue in row["audit_issues"]
    )
    audit_inconsistent = sum(
        row["outcome"] is not None and not row["audit_consistent"] for row in records
    )
    scored_outcomes = Counter(
        row["outcome"]
        for row in records
        if row["audit_consistent"] and row["outcome"] in {"confirm", "wrong"}
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
        "schema_version": int(schema_row["value"]),
        "as_of": as_of_utc.isoformat().replace("+00:00", "Z"),
        "scope": "Newark Home Context local anonymous aggregates",
        "retention_days": retention_days,
        "episodes": len(records),
        "reviewed_denominator": sum(outcome_counts.values()),
        "unreviewed": len(records) - sum(outcome_counts.values()),
        "feedback": {
            "confirmed": outcome_counts["confirm"],
            "wrong": outcome_counts["wrong"],
            "unsure": outcome_counts["unsure"],
            "audit_consistent_scored": sum(scored_outcomes.values()),
            "audit_inconsistent": audit_inconsistent,
            "audit_issue_counts": dict(sorted(audit_issue_counts.items())),
            "scored_accuracy": _accuracy(scored_outcomes["confirm"], scored_outcomes["wrong"]),
        },
        "per_activity_confusion": {
            predicted: dict(sorted(actual_counts.items()))
            for predicted, actual_counts in sorted(confusion.items())
        },
        "confidence_buckets": confidence_buckets,
        "expected_calibration_error": ece,
        "rejected_records": {
            "scope": "database_lifetime",
            "active_distinct": rejected["distinct_count"],
            "pruned_distinct": pruned_values.get("rejected_pruned_distinct", 0),
            "total_distinct": rejected["distinct_count"] + pruned_values.get("rejected_pruned_distinct", 0),
            "active_occurrences": rejected["occurrences"],
            "pruned_occurrences": pruned_values.get("rejected_pruned_occurrences", 0),
            "total_occurrences": rejected["occurrences"] + pruned_values.get("rejected_pruned_occurrences", 0),
        },
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
        f"- Audit-consistent scored feedback: {feedback['audit_consistent_scored']}",
        f"- Audit-inconsistent feedback: {feedback['audit_inconsistent']}",
        f"- Feedback audit issues: {json.dumps(feedback['audit_issue_counts'], sort_keys=True)}",
        f"- Scored accuracy (Unsure and audit failures excluded): {feedback['scored_accuracy']}",
        f"- Rejected records (lifetime distinct / occurrences): {report['rejected_records']['total_distinct']} / {report['rejected_records']['total_occurrences']}",
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
        lines.extend(["| Score | Reviewed | Mean confidence | Observed accuracy | Absolute gap |", "|---|---:|---:|---:|---:|"])
        for bucket, values in report["confidence_buckets"].items():
            lines.append(
                f"| {bucket} | {values['reviewed']} | {values['mean_predicted_confidence']} | {values['observed_accuracy']} | {values['absolute_calibration_gap']} |"
            )
        lines.extend(["", f"Weighted overall ECE: {report['expected_calibration_error']}"])
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
