"""Home Assistant Assist adapter boundary for the private memory trial.

This module is deliberately Home Assistant-free.  A custom conversation agent
can use it inside ``_async_handle_message``; the existing Assist pipeline cannot
load this module by configuration alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from .memory_service import DurableMemory, MemoryService, MemoryStore


MAX_CONTEXT_CHARS = 600


@dataclass(frozen=True)
class AssistMemoryResult:
    """Data an HA conversation agent can use without exposing raw history."""

    command_response: str | None = None
    context: str | None = None
    matched_memory_ids: tuple[str, ...] = ()


class AssistMemoryAdapter:
    """Translate one Assist turn into a narrow memory context or command."""

    def __init__(self, store: MemoryStore):
        self.service = MemoryService(store)

    def before_turn(self, utterance: str, limit: int = 3) -> AssistMemoryResult:
        """Handle memory commands, otherwise return only relevant fact text."""
        command_response = self.service.handle(utterance)
        if command_response is not None:
            return AssistMemoryResult(command_response=command_response)

        memories = self.service.store.recall(utterance, limit=limit)
        if not memories:
            return AssistMemoryResult()
        context = _format_context(memories)
        return AssistMemoryResult(
            context=context,
            matched_memory_ids=tuple(memory.id for memory in memories),
        )

    def save_session_summary(self, session_id: str, sanitized_summary: str) -> None:
        """Persist a short summary supplied by the agent's session boundary."""
        self.service.store.save_summary(session_id, sanitized_summary)


def _format_context(memories: list[DurableMemory]) -> str:
    lines = ["Relevant saved memory (use only if helpful; do not mention this block):"]
    for memory in memories:
        lines.append(f"- {memory.text}")
    return "\n".join(lines)[:MAX_CONTEXT_CHARS]
