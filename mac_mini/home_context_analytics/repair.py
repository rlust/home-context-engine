"""Approval-gated Home Assistant helper repair transactions.

This module defines the transaction and its safety gates. It intentionally has
no Home Assistant transport and no device-service capability; callers must
provide a narrowly scoped managed-helper client.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Protocol

from .diagnostics import (
    DiagnosticFinding,
    DiagnosticReplay,
    IssueStatus,
    detect_signal_issues,
)


class RepairTransactionError(RuntimeError):
    def __init__(self, message: str, audit: tuple["AuditEvent", ...]):
        super().__init__(message)
        self.audit = audit


@dataclass(frozen=True)
class ManagedHelper:
    config_entry_id: str
    config_hash: str
    entity_id: str
    name: str
    device_class: str
    template: str
    source_entity_ids: tuple[str, ...]
    consumers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.config_hash:
            raise ValueError("managed helper config_hash must be non-empty")


class HelperRepairClient(Protocol):
    """Only the managed-helper operations allowed by this transaction."""

    def ai_actions_enabled(self) -> bool: ...

    def fetch_diagnostic_replay(self, helper_entity_id: str) -> DiagnosticReplay: ...

    def fetch_helper(self, config_entry_id: str) -> ManagedHelper: ...

    def update_helper_template(
        self, config_entry_id: str, *, template: str, expected_hash: str
    ) -> None: ...


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    stage: str
    result: str
    detail: str
    config_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "stage": self.stage,
            "result": self.result,
            "detail": self.detail,
            "config_hash": self.config_hash,
        }


@dataclass(frozen=True)
class RepairTransactionResult:
    issue_id: str
    approval_reference: str | None
    status: IssueStatus
    dry_run: bool
    wrote_configuration: bool
    rolled_back: bool
    backup: ManagedHelper
    readback: ManagedHelper
    audit: tuple[AuditEvent, ...]
    physical_canary: str | None
    verification_result: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "approval_reference": self.approval_reference,
            "status": self.status.value,
            "dry_run": self.dry_run,
            "wrote_configuration": self.wrote_configuration,
            "rolled_back": self.rolled_back,
            "backup_hash": self.backup.config_hash,
            "readback_hash": self.readback.config_hash,
            "audit": [event.as_dict() for event in self.audit],
            "physical_canary": self.physical_canary,
            "verification_result": self.verification_result,
        }


@dataclass(frozen=True)
class PhysicalCanaryObservation:
    """Sanitized end-to-end evidence from an owner-observed canary."""

    observed_at: datetime
    replacement_last_updated: datetime
    replacement_state: str
    helper_state: str
    replacement_clear_cycles: int
    helper_clear_cycles: int

    def __post_init__(self) -> None:
        for value in (self.observed_at, self.replacement_last_updated):
            if value.tzinfo is None:
                raise ValueError("canary timestamps must include a timezone")
        valid_states = {"on", "off", "unknown", "unavailable"}
        if self.replacement_state not in valid_states or self.helper_state not in valid_states:
            raise ValueError("canary states must be binary Home Assistant states")
        if self.replacement_clear_cycles < 0 or self.helper_clear_cycles < 0:
            raise ValueError("canary cycle counts cannot be negative")


def verify_physical_canary(
    result: RepairTransactionResult,
    observation: PhysicalCanaryObservation,
    *,
    freshness_window_seconds: int = 300,
    minimum_clear_cycles: int = 2,
) -> RepairTransactionResult:
    """Close a written repair only from fresh, repeated end-to-end evidence.

    A stale candidate is explicitly ``Verification failed`` and is never
    promoted to ``Resolved`` merely because helper readback succeeded.
    """

    if result.status != IssueStatus.VERIFYING or result.dry_run or not result.wrote_configuration:
        raise ValueError("only a written transaction awaiting canary verification can be closed")
    if freshness_window_seconds < 1 or minimum_clear_cycles < 1:
        raise ValueError("canary verification thresholds must be positive")

    events = list(result.audit)
    age_seconds = int((observation.observed_at - observation.replacement_last_updated).total_seconds())
    fresh = 0 <= age_seconds <= freshness_window_seconds
    complete = (
        fresh
        and observation.replacement_state == "off"
        and observation.helper_state == "off"
        and observation.replacement_clear_cycles >= minimum_clear_cycles
        and observation.helper_clear_cycles >= minimum_clear_cycles
    )
    if not fresh:
        detail = (
            "Verification failed: replacement source is stale at canary time "
            f"({max(0, age_seconds)} seconds old; limit {freshness_window_seconds})."
        )
        _audit(events, "verification", "failed", detail)
        return replace(result, status=IssueStatus.VERIFICATION_FAILED, audit=tuple(events), verification_result=detail)
    if not complete:
        detail = (
            "Verification failed: fresh canary did not produce the required "
            f"{minimum_clear_cycles} complete replacement/helper clear cycles."
        )
        _audit(events, "verification", "failed", detail)
        return replace(result, status=IssueStatus.VERIFICATION_FAILED, audit=tuple(events), verification_result=detail)

    detail = (
        "Verification passed: fresh replacement source and Garage Occupied "
        f"completed {minimum_clear_cycles}+ end-to-end clear cycles."
    )
    _audit(events, "verification", "verified", detail)
    return replace(result, status=IssueStatus.RESOLVED, audit=tuple(events), verification_result=detail)


def append_repair_audit(
    path: Path,
    result: RepairTransactionResult,
    *,
    recorded_at: datetime,
) -> None:
    """Append a value-bounded transaction result to an owner-only JSONL log."""

    if recorded_at.tzinfo is None:
        raise ValueError("recorded_at must include a timezone")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        payload = {
            "recorded_at": recorded_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "transaction": result.as_dict(),
        }
        content = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _audit(
    events: list[AuditEvent],
    stage: str,
    result: str,
    detail: str,
    config_hash: str | None = None,
) -> None:
    events.append(AuditEvent(len(events) + 1, stage, result, detail, config_hash))


def _fail(events: list[AuditEvent], stage: str, detail: str) -> None:
    _audit(events, stage, "blocked", detail)
    raise RepairTransactionError(detail, tuple(events))


def _validate_backup(finding: DiagnosticFinding, helper: ManagedHelper) -> None:
    proposal = finding.proposal
    if proposal is None:
        raise ValueError("finding has no executable repair proposal")
    if helper.entity_id != finding.helper_entity_id:
        raise ValueError("fetched helper entity ID does not match the finding")
    if helper.template != proposal.rollback_template:
        raise ValueError("fetched helper template drifted from the proposed rollback definition")
    if helper.template.count(proposal.suspect_source) != 1:
        raise ValueError("fetched helper does not contain exactly one suspect reference")
    if proposal.replacement_source in helper.template:
        raise ValueError("fetched helper already contains the replacement source")
    if helper.consumers != proposal.preserved_consumers:
        raise ValueError("fetched helper consumer inventory drifted")


def _validate_readback(
    finding: DiagnosticFinding,
    backup: ManagedHelper,
    readback: ManagedHelper,
) -> None:
    proposal = finding.proposal
    assert proposal is not None
    if readback.config_hash == backup.config_hash:
        raise ValueError("readback config hash did not change")
    for field in ("config_entry_id", "entity_id", "name", "device_class", "consumers"):
        if getattr(readback, field) != getattr(backup, field):
            raise ValueError(f"readback changed unrelated helper field: {field}")
    if readback.template != proposal.proposed_template:
        raise ValueError("readback template does not equal the approved proposal")
    expected_sources = tuple(
        proposal.replacement_source if item == proposal.suspect_source else item
        for item in backup.source_entity_ids
    )
    if readback.source_entity_ids != expected_sources:
        raise ValueError("readback source inventory changed beyond the approved replacement")


def _rollback(
    client: HelperRepairClient,
    backup: ManagedHelper,
    current: ManagedHelper,
    events: list[AuditEvent],
) -> ManagedHelper:
    _audit(
        events,
        "rollback",
        "started",
        "Restoring the exact fetch-before-write helper definition.",
        current.config_hash,
    )
    try:
        client.update_helper_template(
            backup.config_entry_id,
            template=backup.template,
            expected_hash=current.config_hash,
        )
    except Exception:
        _fail(events, "rollback", "Rollback update failed; helper state requires manual review")
    try:
        restored = client.fetch_helper(backup.config_entry_id)
    except Exception:
        _fail(events, "rollback", "Rollback readback failed; helper state requires manual review")
    if (
        restored.config_entry_id != backup.config_entry_id
        or restored.entity_id != backup.entity_id
        or restored.name != backup.name
        or restored.device_class != backup.device_class
        or restored.template != backup.template
        or restored.source_entity_ids != backup.source_entity_ids
        or restored.consumers != backup.consumers
    ):
        _fail(events, "rollback", "Rollback readback did not restore the exact backup definition")
    _audit(events, "rollback", "verified", "Exact backup restored and read back.", restored.config_hash)
    return restored


def _same_definition(left: ManagedHelper, right: ManagedHelper) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in (
            "config_entry_id",
            "entity_id",
            "name",
            "device_class",
            "template",
            "source_entity_ids",
            "consumers",
        )
    )


def execute_helper_repair(
    finding: DiagnosticFinding,
    client: HelperRepairClient,
    *,
    approved_issue_id: str | None = None,
    approval_reference: str | None = None,
    dry_run: bool = True,
) -> RepairTransactionResult:
    """Execute a helper-only repair; dry-run is intentionally the default."""

    events: list[AuditEvent] = []
    _audit(
        events,
        "proposal",
        "received",
        "Specific helper repair proposal received for validation.",
    )
    if finding.proposal is None:
        _fail(events, "proposal", "Finding is not repairable")
    if not dry_run and approved_issue_id != finding.issue_id:
        _fail(events, "approval", "Live repair requires approval for this exact issue ID")
    if not dry_run and not approval_reference:
        _fail(events, "approval", "Live repair requires a durable owner approval reference")
    _audit(
        events,
        "approval",
        "not_required_for_dry_run" if dry_run else "verified",
        "No write is allowed." if dry_run else "Exact issue approval reference matched.",
    )

    if client.ai_actions_enabled():
        _fail(events, "safety", "AI Actions must remain off")
    _audit(
        events,
        "safety",
        "verified",
        "AI Actions is off; client exposes helper configuration only.",
    )

    fresh_replay = client.fetch_diagnostic_replay(finding.helper_entity_id)
    if fresh_replay.helper.entity_id != finding.helper_entity_id:
        _fail(events, "revalidation", "Fresh replay does not describe the affected helper")
    fresh_findings = detect_signal_issues(fresh_replay)
    fresh = next((item for item in fresh_findings if item.issue_id == finding.issue_id), None)
    if (
        fresh is None
        or fresh.proposal is None
        or fresh.proposal.as_dict() != finding.proposal.as_dict()
    ):
        _fail(events, "revalidation", "Fresh evidence no longer matches the exact repair proposal")
    _audit(
        events,
        "revalidation",
        "verified",
        "Same-device semantics, freshness, cycles, and consumers revalidated.",
    )

    config_entry_id = fresh_replay.helper.config_entry_id
    backup = client.fetch_helper(config_entry_id)
    try:
        _validate_backup(finding, backup)
    except ValueError as exc:
        _fail(events, "fetch_before_write", str(exc))
    _audit(
        events,
        "fetch_before_write",
        "verified",
        "Exact helper backup and fresh config hash captured.",
        backup.config_hash,
    )

    if dry_run:
        _audit(
            events,
            "write",
            "skipped",
            "Dry-run default prevented configuration mutation.",
            backup.config_hash,
        )
        return RepairTransactionResult(
            issue_id=finding.issue_id,
            approval_reference=None,
            status=IssueStatus.APPROVAL_NEEDED,
            dry_run=True,
            wrote_configuration=False,
            rolled_back=False,
            backup=backup,
            readback=backup,
            audit=tuple(events),
            physical_canary=None,
        )

    try:
        client.update_helper_template(
            config_entry_id,
            template=finding.proposal.proposed_template,
            expected_hash=backup.config_hash,
        )
    except Exception:
        _audit(
            events,
            "write",
            "failed",
            "Helper update returned an error; checking readback before deciding rollback.",
            backup.config_hash,
        )
        try:
            uncertain = client.fetch_helper(config_entry_id)
        except Exception:
            _fail(
                events,
                "write",
                "Helper update and safety readback both failed; live state is unknown",
            )
        if _same_definition(uncertain, backup):
            _fail(
                events,
                "write",
                "Helper update failed and readback confirms the backup definition remains loaded",
            )
        try:
            restored = _rollback(client, backup, uncertain, events)
        except RepairTransactionError:
            raise
        except Exception:
            _fail(
                events,
                "rollback",
                "Helper update failed after a possible write and rollback did not complete",
            )
        return RepairTransactionResult(
            issue_id=finding.issue_id,
            approval_reference=approval_reference,
            status=IssueStatus.INVESTIGATE,
            dry_run=False,
            wrote_configuration=True,
            rolled_back=True,
            backup=backup,
            readback=restored,
            audit=tuple(events),
            physical_canary=None,
        )
    _audit(
        events,
        "write",
        "submitted",
        "One helper template reference replacement submitted.",
        backup.config_hash,
    )
    readback = client.fetch_helper(config_entry_id)
    try:
        _validate_readback(finding, backup, readback)
    except ValueError as exc:
        _audit(events, "readback", "failed", str(exc), readback.config_hash)
        restored = _rollback(client, backup, readback, events)
        return RepairTransactionResult(
            issue_id=finding.issue_id,
            approval_reference=approval_reference,
            status=IssueStatus.INVESTIGATE,
            dry_run=False,
            wrote_configuration=True,
            rolled_back=True,
            backup=backup,
            readback=restored,
            audit=tuple(events),
            physical_canary=None,
        )

    _audit(
        events,
        "readback",
        "verified",
        "Approved template and all preserved fields read back exactly.",
        readback.config_hash,
    )
    _audit(
        events,
        "canary",
        "owner_gate",
        "Physical Garage PIR ON-to-clear transition remains required.",
    )
    return RepairTransactionResult(
        issue_id=finding.issue_id,
        approval_reference=approval_reference,
        status=IssueStatus.VERIFYING,
        dry_run=False,
        wrote_configuration=True,
        rolled_back=False,
        backup=backup,
        readback=readback,
        audit=tuple(events),
        physical_canary=(
            "Walk through the Garage PIR field, then verify the replacement source and "
            "Garage Occupied turn on and both clear after the PIR timeout."
        ),
    )
