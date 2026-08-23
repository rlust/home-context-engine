"""Local-only Home Context signal diagnostics and bounded repair proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping


class DiagnosticError(ValueError):
    """Raised when diagnostic input is incomplete or unsafe to interpret."""


class IssueStatus(str, Enum):
    HEALTHY = "Healthy"
    INVESTIGATE = "Investigate"
    REPAIR_PROPOSED = "Repair proposed"
    APPROVAL_NEEDED = "Approval needed"
    VERIFYING = "Verifying"
    VERIFICATION_FAILED = "Verification failed"
    RESOLVED = "Resolved"


class IssueCode(str, Enum):
    STUCK_ACTIVE = "stuck_active"
    SIBLING_DISAGREEMENT = "sibling_disagreement"
    DERIVED_ACTIVE_WITHOUT_CANONICAL_INPUT = "derived_active_without_canonical_input"
    REQUIRED_SOURCE_UNHEALTHY = "required_source_unhealthy"
    HEALTHIER_SAME_DEVICE_CANDIDATE = "healthier_same_device_candidate"


_BINARY_STATES = frozenset({"on", "off", "unknown", "unavailable"})
_COMPATIBLE_DEVICE_CLASSES = frozenset({"motion", "occupancy"})
_SENSITIVE_PARTS = ("camera", "credential", "gps", "latitude", "longitude", "message", "password", "person", "secret", "token")


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise DiagnosticError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DiagnosticError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DiagnosticError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 160:
        raise DiagnosticError(f"{field} must be a non-empty string up to 160 characters")
    lowered = value.lower()
    if any(part in lowered for part in _SENSITIVE_PARTS):
        raise DiagnosticError(f"{field} contains a sensitive identifier")
    return value


@dataclass(frozen=True)
class Transition:
    occurred_at: datetime
    state: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Transition":
        if set(payload) != {"occurred_at", "state"}:
            raise DiagnosticError("transition fields must be occurred_at and state")
        state = payload.get("state")
        if state not in _BINARY_STATES:
            raise DiagnosticError("transition state must be on, off, unknown, or unavailable")
        return cls(_timestamp(payload["occurred_at"], "transition.occurred_at"), state)


@dataclass(frozen=True)
class SignalSample:
    entity_id: str
    device_id: str
    device_class: str
    semantic: str
    required: bool
    max_age_seconds: int | None
    state: str
    last_changed: datetime
    last_updated: datetime
    transitions: tuple[Transition, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SignalSample":
        expected = {
            "entity_id", "device_id", "device_class", "semantic", "required", "max_age_seconds",
            "state", "last_changed", "last_updated", "transitions",
        }
        if set(payload) != expected:
            raise DiagnosticError("signal sample fields do not match the private diagnostic contract")
        state = payload.get("state")
        if state not in _BINARY_STATES:
            raise DiagnosticError("signal state must be on, off, unknown, or unavailable")
        semantic = payload.get("semantic")
        if semantic not in {"event", "state", "occupancy", "door"}:
            raise DiagnosticError("signal semantic is not approved")
        if not isinstance(payload.get("required"), bool):
            raise DiagnosticError("signal required must be boolean")
        max_age_seconds = payload.get("max_age_seconds")
        if max_age_seconds is not None and (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, int)
            or max_age_seconds < 1
        ):
            raise DiagnosticError("signal max_age_seconds must be null or a positive integer")
        raw_transitions = payload.get("transitions")
        if not isinstance(raw_transitions, list):
            raise DiagnosticError("signal transitions must be a list")
        transitions = tuple(Transition.from_payload(item) for item in raw_transitions)
        if tuple(sorted(transitions, key=lambda item: item.occurred_at)) != transitions:
            raise DiagnosticError("signal transitions must be chronological")
        return cls(
            entity_id=_validate_identifier(payload["entity_id"], "entity_id"),
            device_id=_validate_identifier(payload["device_id"], "device_id"),
            device_class=_validate_identifier(payload["device_class"], "device_class"),
            semantic=semantic,
            required=payload["required"],
            max_age_seconds=max_age_seconds,
            state=state,
            last_changed=_timestamp(payload["last_changed"], "last_changed"),
            last_updated=_timestamp(payload["last_updated"], "last_updated"),
            transitions=transitions,
        )

    def completed_cycles(self) -> int:
        return sum(
            previous.state == "on" and current.state == "off"
            for previous, current in zip(self.transitions, self.transitions[1:])
        )


@dataclass(frozen=True)
class HelperSample:
    config_entry_id: str
    entity_id: str
    name: str
    device_class: str
    state: str
    template: str
    source_entity_ids: tuple[str, ...]
    consumers: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "HelperSample":
        expected = {
            "config_entry_id", "entity_id", "name", "device_class", "state",
            "template", "source_entity_ids", "consumers",
        }
        if set(payload) != expected:
            raise DiagnosticError("helper fields do not match the private diagnostic contract")
        if payload.get("state") not in _BINARY_STATES:
            raise DiagnosticError("helper state must be on, off, unknown, or unavailable")
        sources = payload.get("source_entity_ids")
        consumers = payload.get("consumers")
        if not isinstance(sources, list) or not sources:
            raise DiagnosticError("helper must list at least one source")
        if not isinstance(consumers, list):
            raise DiagnosticError("helper consumers must be a list")
        template = payload.get("template")
        if not isinstance(template, str) or not template.strip():
            raise DiagnosticError("helper template must be non-empty")
        return cls(
            config_entry_id=_validate_identifier(payload["config_entry_id"], "config_entry_id"),
            entity_id=_validate_identifier(payload["entity_id"], "helper.entity_id"),
            name=_validate_identifier(payload["name"], "helper.name"),
            device_class=_validate_identifier(payload["device_class"], "helper.device_class"),
            state=payload["state"],
            template=template,
            source_entity_ids=tuple(_validate_identifier(item, "source_entity_id") for item in sources),
            consumers=tuple(_validate_identifier(item, "consumer") for item in consumers),
        )


@dataclass(frozen=True)
class DiagnosticReplay:
    observed_at: datetime
    helper: HelperSample
    signals: tuple[SignalSample, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DiagnosticReplay":
        if set(payload) != {"schema_version", "observed_at", "helper", "signals"}:
            raise DiagnosticError("replay fields do not match the private diagnostic contract")
        if payload.get("schema_version") != 5:
            raise DiagnosticError("diagnostic replay requires schema_version 5")
        raw_signals = payload.get("signals")
        if not isinstance(raw_signals, list):
            raise DiagnosticError("signals must be a list")
        signals = tuple(SignalSample.from_payload(item) for item in raw_signals)
        entity_ids = [signal.entity_id for signal in signals]
        if len(set(entity_ids)) != len(entity_ids):
            raise DiagnosticError("signal entity IDs must be unique")
        helper = HelperSample.from_payload(payload["helper"])
        missing = set(helper.source_entity_ids) - set(entity_ids)
        if missing:
            raise DiagnosticError(f"helper source samples are missing: {', '.join(sorted(missing))}")
        observed_at = _timestamp(payload["observed_at"], "observed_at")
        if any(signal.last_updated > observed_at for signal in signals):
            raise DiagnosticError("signal last_updated cannot be after observed_at")
        return cls(observed_at=observed_at, helper=helper, signals=signals)


@dataclass(frozen=True)
class RepairProposal:
    suspect_source: str
    replacement_source: str
    replacement_reason: str
    proposed_template: str
    rollback_template: str
    preserved_consumers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mutation": {
                "operation": "replace_helper_source_reference",
                "suspect_source": self.suspect_source,
                "replacement_source": self.replacement_source,
            },
            "reason": self.replacement_reason,
            "proposed_template": self.proposed_template,
            "rollback_template": self.rollback_template,
            "preserved_consumers": list(self.preserved_consumers),
        }


@dataclass(frozen=True)
class DiagnosticFinding:
    issue_id: str
    status: IssueStatus
    issue_codes: tuple[IssueCode, ...]
    helper_entity_id: str
    title: str
    explanation: str
    suspect_source: str | None
    suspect_age_seconds: int | None
    comparison_sources: tuple[str, ...]
    ambiguous_candidates: tuple[str, ...]
    downstream_consumers: tuple[str, ...]
    confidence: int
    proposal: RepairProposal | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "status": self.status.value,
            "issue_codes": [code.value for code in self.issue_codes],
            "helper": self.helper_entity_id,
            "title": self.title,
            "explanation": self.explanation,
            "suspect_source": self.suspect_source,
            "suspect_age_seconds": self.suspect_age_seconds,
            "comparison_sources": list(self.comparison_sources),
            "ambiguous_candidates": list(self.ambiguous_candidates),
            "downstream_consumers": list(self.downstream_consumers),
            "confidence": self.confidence,
            "proposal": self.proposal.as_dict() if self.proposal else None,
            "privacy": {
                "raw_transition_history_included": False,
                "person_identity_included": False,
                "camera_audio_messages_gps_included": False,
            },
        }


def _issue_id(helper: str, suspect: str | None, replacement: str | None) -> str:
    value = json.dumps([helper, suspect, replacement], separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compatible(suspect: SignalSample, candidate: SignalSample) -> bool:
    return (
        suspect.entity_id.split(".", 1)[0] == candidate.entity_id.split(".", 1)[0]
        and suspect.device_id == candidate.device_id
        and suspect.device_class in _COMPATIBLE_DEVICE_CLASSES
        and candidate.device_class in _COMPATIBLE_DEVICE_CLASSES
        and candidate.semantic in {"state", "occupancy"}
    )


def _replacement_template(helper: HelperSample, suspect: str, replacement: str) -> str:
    if helper.template.count(suspect) != 1:
        raise DiagnosticError("suspect source must appear exactly once in the helper template")
    if replacement in helper.template:
        raise DiagnosticError("replacement source is already present in the helper template")
    return helper.template.replace(suspect, replacement, 1)


def detect_signal_issues(
    replay: DiagnosticReplay,
    *,
    active_timeout: timedelta = timedelta(minutes=10),
    freshness_window: timedelta = timedelta(minutes=5),
    minimum_clear_cycles: int = 2,
) -> tuple[DiagnosticFinding, ...]:
    """Detect contradictions without performing I/O or mutating HA."""

    if active_timeout <= timedelta(0) or freshness_window <= timedelta(0):
        raise DiagnosticError("diagnostic windows must be positive")
    if minimum_clear_cycles < 1:
        raise DiagnosticError("minimum_clear_cycles must be at least 1")

    helper = replay.helper
    by_id = {signal.entity_id: signal for signal in replay.signals}
    findings: list[DiagnosticFinding] = []

    helper_sources = [by_id[source_id] for source_id in helper.source_entity_ids]
    if helper.state == "on" and all(
        source.state in {"off", "unknown", "unavailable"} for source in helper_sources
    ):
        findings.append(
            DiagnosticFinding(
                issue_id=_issue_id(helper.entity_id, None, None),
                status=IssueStatus.INVESTIGATE,
                issue_codes=(IssueCode.DERIVED_ACTIVE_WITHOUT_CANONICAL_INPUT,),
                helper_entity_id=helper.entity_id,
                title=f"{helper.name} contradicts all canonical inputs",
                explanation="The derived helper is active while every configured input is inactive or unhealthy.",
                suspect_source=None,
                suspect_age_seconds=None,
                comparison_sources=tuple(sorted(helper.source_entity_ids)),
                ambiguous_candidates=(),
                downstream_consumers=helper.consumers,
                confidence=90,
                proposal=None,
            )
        )

    for source_id in helper.source_entity_ids:
        source = by_id[source_id]
        age = replay.observed_at - source.last_changed
        if source.required and (
            source.state in {"unknown", "unavailable"}
            or (
                source.max_age_seconds is not None
                and replay.observed_at - source.last_updated
                > timedelta(seconds=source.max_age_seconds)
            )
        ):
            findings.append(
                DiagnosticFinding(
                    issue_id=_issue_id(helper.entity_id, source.entity_id, None),
                    status=IssueStatus.INVESTIGATE,
                    issue_codes=(IssueCode.REQUIRED_SOURCE_UNHEALTHY,),
                    helper_entity_id=helper.entity_id,
                    title=f"{helper.name} has an unhealthy required source",
                    explanation="A required input is missing, unavailable, or older than its allowed freshness window.",
                    suspect_source=source.entity_id,
                    suspect_age_seconds=max(0, int((replay.observed_at - source.last_updated).total_seconds())),
                    comparison_sources=(),
                    ambiguous_candidates=(),
                    downstream_consumers=helper.consumers,
                    confidence=100,
                    proposal=None,
                )
            )
            continue
        if source.state != "on" or age <= active_timeout:
            continue

        candidates = tuple(
            candidate
            for candidate in replay.signals
            if candidate.entity_id != source.entity_id
            and _compatible(source, candidate)
            and candidate.state == "off"
            and replay.observed_at - candidate.last_updated <= freshness_window
            and candidate.completed_cycles() >= minimum_clear_cycles
        )
        if not candidates:
            continue

        codes = [IssueCode.STUCK_ACTIVE, IssueCode.SIBLING_DISAGREEMENT]
        remaining_required = [
            by_id[item]
            for item in helper.source_entity_ids
            if item != source.entity_id and by_id[item].required
        ]
        if helper.state == "on" and all(
            item.state in {"off", "unknown", "unavailable"} for item in remaining_required
        ):
            codes.append(IssueCode.DERIVED_ACTIVE_WITHOUT_CANONICAL_INPUT)

        candidate_ids = tuple(sorted(candidate.entity_id for candidate in candidates))
        if len(candidates) != 1:
            findings.append(
                DiagnosticFinding(
                    issue_id=_issue_id(helper.entity_id, source.entity_id, None),
                    status=IssueStatus.INVESTIGATE,
                    issue_codes=tuple(codes),
                    helper_entity_id=helper.entity_id,
                    title=f"{helper.name} has ambiguous same-device replacements",
                    explanation="Multiple compatible sources have fresh clearing evidence; no repair is safe without owner review.",
                    suspect_source=source.entity_id,
                    suspect_age_seconds=int(age.total_seconds()),
                    comparison_sources=candidate_ids,
                    ambiguous_candidates=candidate_ids,
                    downstream_consumers=helper.consumers,
                    confidence=60,
                    proposal=None,
                )
            )
            continue

        candidate = candidates[0]
        codes.append(IssueCode.HEALTHIER_SAME_DEVICE_CANDIDATE)
        proposal = RepairProposal(
            suspect_source=source.entity_id,
            replacement_source=candidate.entity_id,
            replacement_reason=(
                "Same device and compatible motion semantics; fresh state source completed "
                f"{candidate.completed_cycles()} observed on-to-off cycles."
            ),
            proposed_template=_replacement_template(helper, source.entity_id, candidate.entity_id),
            rollback_template=helper.template,
            preserved_consumers=helper.consumers,
        )
        findings.append(
            DiagnosticFinding(
                issue_id=_issue_id(helper.entity_id, source.entity_id, candidate.entity_id),
                status=IssueStatus.REPAIR_PROPOSED,
                issue_codes=tuple(codes),
                helper_entity_id=helper.entity_id,
                title=f"{helper.name} falsely active",
                explanation=(
                    "The event-style output stayed on after the same device's state-style output cleared. "
                    "Replace only the stale source reference and preserve the helper identity and other inputs."
                ),
                suspect_source=source.entity_id,
                suspect_age_seconds=int(age.total_seconds()),
                comparison_sources=(candidate.entity_id,),
                ambiguous_candidates=(),
                downstream_consumers=helper.consumers,
                confidence=95,
                proposal=proposal,
            )
        )

    return tuple(sorted(findings, key=lambda finding: finding.issue_id))


def diagnostic_report_payload(replay: DiagnosticReplay, findings: Iterable[DiagnosticFinding]) -> dict[str, Any]:
    """Return schema-5 private report content without raw household history."""

    materialized = tuple(findings)
    overall_status = IssueStatus.HEALTHY
    if any(finding.status == IssueStatus.REPAIR_PROPOSED for finding in materialized):
        overall_status = IssueStatus.REPAIR_PROPOSED
    elif materialized:
        overall_status = IssueStatus.INVESTIGATE
    return {
        "schema_version": 5,
        "observed_at": _timestamp_text(replay.observed_at),
        "scope": "Newark Home Context private signal diagnostics",
        "helper_count": 1,
        "issue_count": len(materialized),
        "overall_status": overall_status.value,
        "issues": [finding.as_dict() for finding in materialized],
        "privacy": {
            "local_only": True,
            "raw_transition_history_included": False,
            "network_used": False,
        },
    }
