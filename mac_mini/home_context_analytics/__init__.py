"""Deterministic, local-only analytics for Newark Home Context."""

from .collector import collect_continuous_file, collect_jsonl
from .report import build_report
from .normalizer import NormalizerState, normalize_and_append, normalize_snapshot

__all__ = [
    "build_report",
    "collect_continuous_file",
    "collect_jsonl",
    "NormalizerState",
    "normalize_and_append",
    "normalize_snapshot",
]
