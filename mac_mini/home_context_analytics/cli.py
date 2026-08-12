"""Command-line entry point for the offline collector and report generator."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .collector import collect_continuous_file, collect_jsonl
from .model import ValidationError, parse_timestamp
from .normalizer import NormalizerState, SnapshotError, normalize_and_append
from .report import build_report, report_json, report_markdown


def _datetime(value: str) -> datetime:
    normalized = parse_timestamp(value, "as_of")
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="home-context-analytics",
        description="Local-only Newark Home Context transition analytics",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="ingest a local normalized JSONL file")
    ingest.add_argument("--input", required=True, help="JSONL path, or - for stdin")
    ingest.add_argument("--database", required=True, type=Path)
    ingest.add_argument("--retention-days", type=int, default=45)
    ingest.add_argument("--drift-window-days", type=int, default=14)
    ingest.add_argument("--as-of", type=_datetime, default=None)

    continuous = commands.add_parser(
        "ingest-continuous", help="checkpointed append-only ingest with fault isolation"
    )
    continuous.add_argument("--input", required=True, type=Path)
    continuous.add_argument("--database", required=True, type=Path)
    continuous.add_argument("--retention-days", type=int, default=45)
    continuous.add_argument("--drift-window-days", type=int, default=14)
    continuous.add_argument("--max-quarantine-distinct", type=int, default=1000)
    continuous.add_argument("--as-of", type=_datetime, default=None)

    normalize = commands.add_parser(
        "normalize-snapshot", help="normalize one supplied Newark snapshot and append JSONL"
    )
    normalize.add_argument("--input", required=True, type=Path)
    normalize.add_argument("--state-database", required=True, type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    normalize.add_argument("--output-mode", choices=("append", "atomic-replace"), default="append")

    report = commands.add_parser("report", help="produce deterministic local aggregates")
    report.add_argument("--database", required=True, type=Path)
    report.add_argument("--as-of", required=True, type=_datetime)
    report.add_argument("--window-days", type=int, default=14)
    report.add_argument("--format", choices=("json", "markdown"), default="json")
    report.add_argument("--output", type=Path, default=None, help="local file; stdout when omitted")
    return parser


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "ingest":
            if args.retention_days < 1:
                raise ValidationError("retention-days must be at least 1")
            if args.input == "-":
                counts = collect_jsonl(
                    sys.stdin,
                    args.database,
                    retention_days=args.retention_days,
                    drift_window_days=args.drift_window_days,
                    as_of=args.as_of,
                )
            else:
                with Path(args.input).open("r", encoding="utf-8") as stream:
                    counts = collect_jsonl(
                        stream,
                        args.database,
                        retention_days=args.retention_days,
                        drift_window_days=args.drift_window_days,
                        as_of=args.as_of,
                    )
            sys.stdout.write(json.dumps(counts, sort_keys=True) + "\n")
            return 0

        if args.command == "ingest-continuous":
            counts = collect_continuous_file(
                args.input,
                args.database,
                retention_days=args.retention_days,
                drift_window_days=args.drift_window_days,
                max_quarantine_distinct=args.max_quarantine_distinct,
                as_of=args.as_of,
            )
            sys.stdout.write(json.dumps(counts, sort_keys=True) + "\n")
            return 0

        if args.command == "normalize-snapshot":
            with args.input.open("r", encoding="utf-8") as stream:
                snapshot = json.load(stream)
            with NormalizerState(args.state_database) as state:
                result = normalize_and_append(
                    snapshot,
                    state,
                    args.output,
                    output_mode=args.output_mode,
                )
            sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
            return 0

        report = build_report(args.database, as_of=args.as_of, window_days=args.window_days)
        content = report_json(report) if args.format == "json" else report_markdown(report)
        if args.output:
            _write_private(args.output, content)
        else:
            sys.stdout.write(content)
        return 0
    except (FileNotFoundError, json.JSONDecodeError, OSError, RuntimeError, SnapshotError, ValidationError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
