"""Sanitized dashboard payloads for Home Context signal diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .diagnostics import DiagnosticFinding, IssueStatus


_STAGE_STATUS = {
    "detected": IssueStatus.INVESTIGATE,
    "proposal_ready": IssueStatus.REPAIR_PROPOSED,
    "approval_pending": IssueStatus.APPROVAL_NEEDED,
    "verifying": IssueStatus.VERIFYING,
    "verification_failed": IssueStatus.VERIFICATION_FAILED,
    "resolved": IssueStatus.RESOLVED,
    "rolled_back": IssueStatus.INVESTIGATE,
}


@dataclass(frozen=True)
class IssueCardState:
    finding: DiagnosticFinding
    stage: str
    updated_at: datetime
    approval_reference: str | None = None
    verification_result: str | None = None
    rollback_result: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in _STAGE_STATUS:
            raise ValueError(f"unsupported issue-card stage: {self.stage}")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must include a timezone")
        if self.stage in {"verifying", "verification_failed", "resolved"} and not self.approval_reference:
            raise ValueError("verification and resolution require an approval reference")
        if self.stage in {"verification_failed", "resolved"} and not self.verification_result:
            raise ValueError("verification failure and resolution require a verification result")
        if self.stage == "rolled_back" and not self.rollback_result:
            raise ValueError("rolled_back requires a rollback result")


def build_issue_card_payload(state: IssueCardState) -> dict[str, Any]:
    """Build a compact card payload with an explicit repair lifecycle."""

    finding = state.finding
    proposal = finding.proposal
    status = _STAGE_STATUS[state.stage]
    stages = (
        ("Detection", "detected"),
        ("Proposal", "proposal_ready"),
        ("Approval", "approval_pending"),
        ("Verification", "verifying"),
        ("Resolution", "resolved"),
        ("Rollback", "rolled_back"),
    )
    current_index = (
        [item[1] for item in stages].index(state.stage)
        if state.stage != "verification_failed"
        else None
    )
    lifecycle = []
    for index, (label, key) in enumerate(stages):
        if state.stage == "verification_failed":
            if key in {"detected", "proposal_ready", "approval_pending"}:
                phase_state = "complete"
            elif key == "verifying":
                phase_state = "failed"
            elif key == "resolved":
                phase_state = "not_reached"
            else:
                phase_state = "available"
        elif key == "rolled_back":
            phase_state = "complete" if state.stage == "rolled_back" else "available"
        elif state.stage == "rolled_back":
            phase_state = "complete" if key in {"detected", "proposal_ready", "approval_pending", "verifying"} else "not_reached"
        else:
            phase_state = "current" if index == current_index else ("complete" if index < current_index else "pending")
        lifecycle.append({"label": label, "key": key, "state": phase_state})

    return {
        "issue_id": finding.issue_id,
        "state": status.value,
        "stage": state.stage,
        "title": finding.title,
        "affected_helper": finding.helper_entity_id,
        "suspect_source": finding.suspect_source,
        "suspect_age_seconds": finding.suspect_age_seconds,
        "comparison_sources": list(finding.comparison_sources),
        "downstream_effect": list(finding.downstream_consumers),
        "evidence": finding.explanation,
        "confidence": finding.confidence,
        "proposed_mutation": proposal.as_dict()["mutation"] if proposal else None,
        "rollback_available": proposal is not None,
        "approval": {
            "required": proposal is not None,
            "reference": state.approval_reference,
            "apply_enabled": state.stage == "approval_pending" and bool(state.approval_reference),
        },
        "verification": {
            "result": state.verification_result,
            "failed": state.stage == "verification_failed",
            "physical_canary_pending": state.stage == "verifying" and state.verification_result is None,
        },
        "rollback": {"result": state.rollback_result},
        "lifecycle": lifecycle,
        "safety": {
            "ai_actions": "OFF",
            "device_controls_available": False,
            "dry_run_default": True,
        },
        "updated_at": state.updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
