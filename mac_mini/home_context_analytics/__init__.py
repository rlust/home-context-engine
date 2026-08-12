"""Deterministic, local-only analytics for Newark Home Context."""

from .collector import collect_jsonl
from .report import build_report

__all__ = ["build_report", "collect_jsonl"]
