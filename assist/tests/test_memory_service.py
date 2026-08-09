import json
from datetime import datetime, timedelta, timezone

import pytest

from assist.adapter import AssistMemoryAdapter
from assist.memory_service import MemoryService, MemoryStore


def test_explicit_save_and_scoped_recall(tmp_path):
    service = MemoryService(MemoryStore(tmp_path / "memory.json"))
    assert service.handle("My name is Randy") is None
    assert service.handle("Remember that my name is Randy") == "Okay, I'll remember that."
    assert [m.text for m in service.store.recall("What is my name?")] == ["my name is Randy"]
    assert service.store.recall("garage lights") == []


def test_broad_recall_can_list_explicitly_saved_facts(tmp_path):
    service = MemoryService(MemoryStore(tmp_path / "memory.json"))
    service.handle("Remember that I prefer jazz")
    assert "I prefer jazz" in service.handle("What do you remember?")


def test_sensitive_content_is_not_saved(tmp_path):
    service = MemoryService(MemoryStore(tmp_path / "memory.json"))
    assert "won't save" in service.handle("Remember my Wi-Fi password is hunter2")
    assert service.store.recall("password") == []


def test_forget_is_audited_and_removes_matching_memory(tmp_path):
    store = MemoryStore(tmp_path / "memory.json")
    store.save_memory("Randy prefers jazz", ["preference"])
    store.save_memory("Kim likes tea", ["preference"])
    assert store.forget("jazz") == 1
    assert [m.text for m in store.recall("preference")] == ["Kim likes tea"]
    audit = (tmp_path / "memory.json.audit.jsonl").read_text()
    assert '"action": "forget_memory"' in audit


def test_summary_rolls_forward_per_session_and_expires(tmp_path):
    store = MemoryStore(tmp_path / "memory.json", rolling_days=30)
    old = datetime.now(timezone.utc) - timedelta(days=31)
    store.save_summary("old", "Old conversation", old)
    store.save_summary("current", "Current conversation")
    assert store.latest_summary().text == "Current conversation"
    data = json.loads((tmp_path / "memory.json").read_text())
    assert [item["session_id"] for item in data["summaries"]] == ["current"]


def test_summary_rejects_sensitive_content(tmp_path):
    store = MemoryStore(tmp_path / "memory.json")
    with pytest.raises(ValueError):
        store.save_summary("s", "The API key is abc")


def test_assist_adapter_returns_only_relevant_context(tmp_path):
    adapter = AssistMemoryAdapter(MemoryStore(tmp_path / "memory.json"))
    adapter.service.store.save_memory("I prefer jazz", ["music"])
    result = adapter.before_turn("What music should I play?")
    assert result.command_response is None
    assert result.context is not None and "I prefer jazz" in result.context
    assert "password" not in result.context.lower()
    assert adapter.before_turn("How is the garage?").context is None


def test_assist_adapter_keeps_memory_commands_out_of_context(tmp_path):
    adapter = AssistMemoryAdapter(MemoryStore(tmp_path / "memory.json"))
    result = adapter.before_turn("Remember that I like tea")
    assert result.command_response == "Okay, I'll remember that."
    assert result.context is None
