"""Deterministic, local-only analytics for Newark Home Context."""

from .collector import collect_continuous_file, collect_jsonl
from .diagnostics import DiagnosticReplay, detect_signal_issues, diagnostic_report_payload
from .issue_card import IssueCardState, build_issue_card_payload
from .repair import (
    ManagedHelper,
    RepairTransactionResult,
    append_repair_audit,
    execute_helper_repair,
)
from .report import build_report
from .normalizer import NormalizerState, normalize_and_append, normalize_snapshot

__all__ = [
    "build_report",
    "collect_continuous_file",
    "collect_jsonl",
    "DiagnosticReplay",
    "detect_signal_issues",
    "diagnostic_report_payload",
    "IssueCardState",
    "build_issue_card_payload",
    "ManagedHelper",
    "RepairTransactionResult",
    "append_repair_audit",
    "execute_helper_repair",
    "NormalizerState",
    "normalize_and_append",
    "normalize_snapshot",
]
