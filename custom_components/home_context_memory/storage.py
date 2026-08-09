"""Async HA Store-backed memory primitives."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from homeassistant.helpers.storage import Store

from .const import DEFAULT_MAX_RESULTS, DEFAULT_ROLLING_DAYS, STORAGE_KEY, STORAGE_VERSION

_SENSITIVE = (
    re.compile(r"\b(password|passphrase|secret|token|api[ _-]?key|private key)\b", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\b(?:ssn|social security|credit card|bank account)\b", re.I),
)
_WORDS = re.compile(r"[a-z0-9']+")

# Small, intentional vocabulary bridges for relationship-aware recall. These
# expand the query only; stored text is never broadened and result limits still
# apply. Explicit room/light names continue to match through normal token
# overlap (for example, "living room" or "kitchen light").
_CONTEXT_EXPANSIONS = {
    "family": {
        "family", "household", "person", "people", "name", "names",
        "wife", "husband", "spouse", "child", "children", "kid", "kids",
        "dog", "cat", "pet", "pets",
    },
    "household": {
        "family", "household", "person", "people", "name", "names",
        "wife", "husband", "spouse", "child", "children", "kid", "kids",
        "dog", "cat", "pet", "pets",
    },
    "room": {"room", "rooms", "area", "areas", "light", "lights", "lighting"},
    "rooms": {"room", "rooms", "area", "areas", "light", "lights", "lighting"},
    "light": {"room", "rooms", "area", "areas", "light", "lights", "lighting"},
    "lights": {"room", "rooms", "area", "areas", "light", "lights", "lighting"},
    "lighting": {"room", "rooms", "area", "areas", "light", "lights", "lighting"},
}


def is_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE)


def _words(text: str) -> set[str]:
    return {word for word in _WORDS.findall(text.lower()) if len(word) > 2}


def _expand_query_words(query_words: set[str]) -> set[str]:
    """Add narrowly scoped semantic category terms to a recall query."""
    expanded = set(query_words)
    for word in query_words:
        expanded.update(_CONTEXT_EXPANSIONS.get(word, ()))
    return expanded


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class MemoryStore:
    """Persist facts and summaries through Home Assistant's Store helper."""

    def __init__(self, hass, rolling_days: int = DEFAULT_ROLLING_DAYS):
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict | None = None
        self.rolling_days = rolling_days

    async def _get(self) -> dict:
        if self._data is None:
            self._data = await self._store.async_load() or {"memories": [], "summaries": []}
        self._data.setdefault("memories", [])
        self._data.setdefault("summaries", [])
        return self._data

    async def _save(self) -> None:
        await self._store.async_save(self._data)

    async def save_memory(self, text: str, tags: list[str] | None = None) -> bool:
        text = text.strip()
        if not text or is_sensitive(text):
            return False
        data = await self._get()
        stamp = _now().isoformat()
        data["memories"].append({"id": f"memory-{int(_now().timestamp() * 1000)}", "text": text,
                                  "created_at": stamp, "updated_at": stamp,
                                  "tags": sorted(set(tags or []))})
        await self._save()
        return True

    async def recall(self, query: str, limit: int = DEFAULT_MAX_RESULTS) -> list[dict]:
        data = await self._get()
        query_words = _expand_query_words(_words(query))
        scored = []
        for item in data["memories"]:
            score = len(query_words & _words(item["text"] + " " + " ".join(item.get("tags", []))))
            if score:
                scored.append((score, _parse(item["updated_at"]), item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [item for _, _, item in scored[:max(0, limit)]]

    async def list_memories(self, limit: int = DEFAULT_MAX_RESULTS) -> list[dict]:
        data = await self._get()
        return sorted(data["memories"], key=lambda item: _parse(item["updated_at"]), reverse=True)[:max(0, limit)]

    async def forget(self, query: str) -> int:
        data = await self._get()
        query_words = _words(query)
        before = len(data["memories"])
        data["memories"] = [item for item in data["memories"]
                             if not query_words & _words(item["text"] + " " + " ".join(item.get("tags", [])))]
        removed = before - len(data["memories"])
        if removed:
            await self._save()
        return removed

    async def save_summary(self, session_id: str, text: str) -> bool:
        text = text.strip()
        if not text or is_sensitive(text):
            return False
        data = await self._get()
        cutoff = _now() - timedelta(days=self.rolling_days)
        data["summaries"] = [item for item in data["summaries"] if _parse(item["updated_at"]) >= cutoff]
        data["summaries"] = [item for item in data["summaries"] if item["session_id"] != session_id]
        data["summaries"].append({"session_id": session_id, "text": text, "updated_at": _now().isoformat()})
        await self._save()
        return True

    async def latest_summary(self) -> dict | None:
        data = await self._get()
        cutoff = _now() - timedelta(days=self.rolling_days)
        current = [item for item in data["summaries"] if _parse(item["updated_at"]) >= cutoff]
        if current != data["summaries"]:
            data["summaries"] = current
            await self._save()
        return max(current, key=lambda item: _parse(item["updated_at"]), default=None)
