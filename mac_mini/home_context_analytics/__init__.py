"""Deterministic, local-only analytics for Newark Home Context."""

from .collector import collect_continuous_file, collect_jsonl
from .report import build_report

__all__ = ["build_report", "collect_continuous_file", "collect_jsonl"]
