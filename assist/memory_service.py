"""Private, observe-only conversational memory trial.

The service is intentionally independent of Home Assistant.  Assist can call
the small command-facing API in :class:`MemoryService`; this module never
calls an HA service or changes an entity.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROLLING_DAYS = 30
SENSITIVE_PATTERNS = (
    re.compile(r"\b(password|passphrase|secret|token|api[ _-]?key|private key)\b", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\b(?:ssn|social security|credit card|bank account)\b", re.I),
)
WORD_RE = re.compile(r"[a-z0-9']+")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def is_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def words(text: str) -> set[str]:
    return {word for word in WORD_RE.findall(text.lower()) if len(word) > 2}


@dataclass
class DurableMemory:
    id: str
    text: str
    created_at: str
    updated_at: str
    tags: list[str]


@dataclass
class ConversationSummary:
    session_id: str
    text: str
    updated_at: str


class MemoryStore:
    """Small JSON store with atomic replacement and an append-only audit log."""

    def __init__(self, path: str | Path, rolling_days: int = DEFAULT_ROLLING_DAYS):
        self.path = Path(path)
        self.audit_path = self.path.with_suffix(self.path.suffix + ".audit.jsonl")
        self.rolling_days = rolling_days
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"memories": [], "summaries": []}
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"memory store is unreadable: {self.path}") from exc

    def _write(self, data: dict) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(4)}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def _audit(self, action: str, **details: str) -> None:
        event = {"at": iso(now_utc()), "action": action, **details}
        with self.audit_path.open("a") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def expire(self, now: datetime | None = None) -> int:
        now = now or now_utc()
        data = self._read()
        cutoff = now - timedelta(days=self.rolling_days)
        before = len(data["summaries"])
        data["summaries"] = [
            item for item in data["summaries"] if parse_time(item["updated_at"]) >= cutoff
        ]
        removed = before - len(data["summaries"])
        if removed:
            self._write(data)
            self._audit("expire_summaries", removed=str(removed))
        return removed

    def save_memory(self, text: str, tags: Iterable[str] = ()) -> DurableMemory:
        text = text.strip()
        if not text:
            raise ValueError("memory text cannot be empty")
        if is_sensitive(text):
            raise ValueError("memory declined: it appears to contain sensitive information")
        data = self._read()
        timestamp = iso(now_utc())
        memory = DurableMemory(secrets.token_urlsafe(9), text, timestamp, timestamp, sorted(set(tags)))
        data["memories"].append(asdict(memory))
        self._write(data)
        self._audit("save_memory", memory_id=memory.id)
        return memory

    def recall(self, query: str, limit: int = 5) -> list[DurableMemory]:
        query_words = words(query)
        scored = []
        for item in self._read()["memories"]:
            memory = DurableMemory(**item)
            score = len(query_words & words(memory.text + " " + " ".join(memory.tags)))
            if score:
                scored.append((score, parse_time(memory.updated_at), memory))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [memory for _, _, memory in scored[: max(0, limit)]]

    def list_memories(self, limit: int = 5) -> list[DurableMemory]:
        """Return recent durable facts for an explicit broad recall request."""
        memories = [DurableMemory(**item) for item in self._read()["memories"]]
        memories.sort(key=lambda memory: parse_time(memory.updated_at), reverse=True)
        return memories[: max(0, limit)]

    def forget(self, query: str) -> int:
        query_words = words(query)
        data = self._read()
        kept = []
        removed = 0
        for item in data["memories"]:
            if query_words and query_words & words(item["text"] + " " + " ".join(item.get("tags", []))):
                removed += 1
            else:
                kept.append(item)
        if removed:
            data["memories"] = kept
            self._write(data)
            self._audit("forget_memory", query=query, removed=str(removed))
        return removed

    def save_summary(self, session_id: str, text: str, now: datetime | None = None) -> None:
        text = text.strip()
        if not text or is_sensitive(text):
            raise ValueError("summary declined: empty or sensitive content")
        self.expire(now)
        data = self._read()
        timestamp = iso(now or now_utc())
        data["summaries"] = [item for item in data["summaries"] if item["session_id"] != session_id]
        data["summaries"].append(asdict(ConversationSummary(session_id, text, timestamp)))
        self._write(data)
        self._audit("save_summary", session_id=session_id)

    def latest_summary(self, now: datetime | None = None) -> ConversationSummary | None:
        self.expire(now)
        items = self._read()["summaries"]
        if not items:
            return None
        return ConversationSummary(**max(items, key=lambda item: parse_time(item["updated_at"])))


class MemoryService:
    """Plain-language boundary for an Assist adapter."""

    def __init__(self, store: MemoryStore):
        self.store = store

    def handle(self, text: str) -> str | None:
        normalized = text.strip()
        lowered = normalized.lower()
        if lowered.startswith(("remember that ", "remember ")):
            fact = re.sub(r"^remember(?: that)?\s+", "", normalized, flags=re.I)
            try:
                self.store.save_memory(fact)
            except ValueError:
                return "I won't save that because it may contain sensitive information."
            return "Okay, I'll remember that."
        if lowered.startswith(("forget ", "delete memory ")):
            query = re.sub(r"^(?:forget|delete memory)\s+", "", normalized, flags=re.I)
            return f"I forgot {self.store.forget(query)} matching memory."
        if lowered in {"what do you remember", "what do you remember?", "recall"}:
            summary = self.store.latest_summary()
            memories = self.store.list_memories(5)
            if not memories and not summary:
                return "I don't have any saved memories yet."
            parts = ([f"Recent conversation: {summary.text}"] if summary else [])
            parts.extend(f"- {memory.text}" for memory in memories)
            return "\n".join(parts)
        return None
