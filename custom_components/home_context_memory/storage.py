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
_TOPIC_WORDS = {
    "family": {"family", "household", "wife", "husband", "spouse", "child", "dog", "cat", "pet"},
    "rooms": {"room", "rooms", "area", "areas"},
    "lighting": {"light", "lights", "lighting", "lamp", "lamps"},
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


def _topics(text: str) -> list[str]:
    """Return only broad, non-content topic labels for dashboard metadata."""
    words = _words(text)
    return sorted(topic for topic, terms in _TOPIC_WORDS.items() if words & terms)


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
        self._data.setdefault("audit", [])
        return self._data

    async def _save(self) -> None:
        await self._store.async_save(self._data)

    async def _audit(self, action: str, scope: str, count: int = 0) -> None:
        data = await self._get()
        data["audit"].append({"action": action, "scope": scope, "count": count,
                              "at": _now().isoformat()})
        data["audit"] = data["audit"][-50:]
        await self._save()

    async def _prune_summaries(self, data: dict) -> bool:
        cutoff = _now() - timedelta(days=self.rolling_days)
        current = [item for item in data["summaries"] if _parse(item["updated_at"]) >= cutoff]
        if current != data["summaries"]:
            removed = len(data["summaries"]) - len(current)
            data["summaries"] = current
            await self._audit("expire", "summaries", removed)
            return True
        return False

    async def save_memory(self, text: str, tags: list[str] | None = None) -> bool:
        text = text.strip()
        if not text or is_sensitive(text):
            return False
        data = await self._get()
        stamp = _now().isoformat()
        data["memories"].append({"id": f"memory-{int(_now().timestamp() * 1000)}", "text": text,
                                  "created_at": stamp, "updated_at": stamp,
                                  "tags": sorted(set(tags or []) | set(_topics(text)))})
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
        results = [item for _, _, item in scored[:max(0, limit)]]
        await self._audit("recall", "scoped", len(results))
        return results

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
        await self._audit("forget", "memories", removed)
        return removed

    async def clear_memories(self) -> int:
        data = await self._get()
        removed = len(data["memories"])
        data["memories"] = []
        await self._audit("clear", "memories", removed)
        return removed

    async def forget_summaries(self, query: str) -> int:
        data = await self._get()
        query_words = _words(query)
        before = len(data["summaries"])
        if query_words:
            data["summaries"] = [item for item in data["summaries"]
                                  if not query_words & _words(item["text"] + " " + " ".join(item.get("tags", [])))]
        else:
            data["summaries"] = []
        removed = before - len(data["summaries"])
        await self._audit("forget", "summaries", removed)
        return removed

    async def clear_summaries(self) -> int:
        return await self.forget_summaries("")

    async def save_summary(self, session_id: str, text: str) -> bool:
        text = text.strip()
        if not text or is_sensitive(text):
            return False
        data = await self._get()
        await self._prune_summaries(data)
        data["summaries"] = [item for item in data["summaries"] if item["session_id"] != session_id]
        data["summaries"].append({"session_id": session_id, "text": text, "updated_at": _now().isoformat(),
                                   "tags": _topics(text)})
        await self._save()
        return True

    async def recall_summary(self, query: str) -> dict | None:
        data = await self._get()
        await self._prune_summaries(data)
        query_words = _expand_query_words(_words(query))
        matches = []
        for item in data["summaries"]:
            score = len(query_words & _words(item["text"] + " " + " ".join(item.get("tags", []))))
            if score:
                matches.append((score, _parse(item["updated_at"]), item))
        matches.sort(key=lambda row: (row[0], row[1]), reverse=True)
        result = matches[0][2] if matches else None
        await self._audit("summary_recall", "scoped", 1 if result else 0)
        return result

    async def latest_summary(self) -> dict | None:
        data = await self._get()
        await self._prune_summaries(data)
        current = data["summaries"]
        return max(current, key=lambda item: _parse(item["updated_at"]), default=None)

    async def status(self) -> dict:
        data = await self._get()
        await self._prune_summaries(data)
        latest = max(data["summaries"], key=lambda item: _parse(item["updated_at"]), default=None)
        topic_counts: dict[str, int] = {}
        for item in data["memories"] + data["summaries"]:
            for topic in item.get("tags", []):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        audit = data["audit"][-1] if data["audit"] else None
        context = data.get("context_brief") or {}
        return {"memory_count": len(data["memories"]), "summary_count": len(data["summaries"]),
                "latest_summary_at": latest["updated_at"] if latest else None,
                "summary_expires_at": (_parse(latest["updated_at"]) + timedelta(days=self.rolling_days)).isoformat()
                if latest else None, "topic_counts": topic_counts, "last_action": audit,
                "context_brief_supplied": bool(context.get("supplied")),
                "context_brief_categories": context.get("categories", []),
                "context_brief_sources": context.get("sources", []),
                "context_brief_memory_count": int(context.get("memory_count", 0)),
                "context_brief_at": context.get("at")}

    async def record_context_brief(self, categories: tuple[str, ...], sources: tuple[str, ...], memory_count: int) -> None:
        """Record context provenance without storing brief contents."""
        data = await self._get()
        stamp = _now().isoformat()
        data["context_brief"] = {"supplied": True, "categories": list(categories),
                                 "sources": list(sources), "memory_count": memory_count, "at": stamp}
        data["audit"].append({"action": "context_brief", "scope": "metadata", "count": memory_count,
                              "categories": list(categories), "sources": list(sources), "at": stamp})
        data["audit"] = data["audit"][-50:]
        await self._save()
