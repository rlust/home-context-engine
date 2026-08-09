import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "home_context_memory"


def test_hacs_metadata_and_manifest_are_valid():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert hacs["content_in_root"] is False
    assert manifest["domain"] == "home_context_memory"
    for key in ("documentation", "issue_tracker", "codeowners", "name", "version"):
        assert manifest[key]


def test_package_has_one_integration_and_compiles():
    integration_dirs = [path for path in (ROOT / "custom_components").iterdir() if path.is_dir()]
    assert [path.name for path in integration_dirs] == ["home_context_memory"]
    for path in INTEGRATION.glob("*.py"):
        ast.parse(path.read_text(), filename=str(path))


def test_conversation_agent_has_no_service_or_device_control_calls():
    source = (INTEGRATION / "conversation.py").read_text()
    assert "async_call" not in source
    assert "hass.services" not in source
    assert "execute_service" not in source


def test_conversation_agent_implements_current_supported_languages_api():
    tree = ast.parse((INTEGRATION / "conversation.py").read_text())
    entity = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "HomeContextMemoryConversationEntity"
    )
    method = next(
        node
        for node in entity.body
        if isinstance(node, ast.FunctionDef) and node.name == "supported_languages"
    )
    assert any(
        isinstance(decorator, ast.Name) and decorator.id == "property"
        for decorator in method.decorator_list
    )
    assert any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value == "*"
        for node in ast.walk(method)
    )


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9']+", text.lower()) if len(word) > 2}


def test_family_recall_matches_explicit_relationship_memories():
    expansions = _literal_assignment(INTEGRATION / "storage.py", "_CONTEXT_EXPANSIONS")
    saved = [
        "my name is Example",
        "my wife's name is Example",
        "my dog's name is Example",
    ]
    query_words = _words("What do you remember about my family?")
    for word in tuple(query_words):
        query_words.update(expansions.get(word, ()))

    matches = [text for text in saved if query_words & _words(text)]
    assert matches == saved


def test_room_light_recall_matches_category_and_related_room_queries():
    expansions = _literal_assignment(INTEGRATION / "storage.py", "_CONTEXT_EXPANSIONS")
    saved = "Please remember that the living room light should stay warm"

    category_query = _words("What do you remember about lighting?")
    for word in tuple(category_query):
        category_query.update(expansions.get(word, ()))
    related_query = _words("What do you remember about the living room?")

    assert category_query & _words(saved)
    assert related_query & _words(saved)


def test_continuity_is_expiring_filtered_and_scoped():
    storage = (INTEGRATION / "storage.py").read_text()
    conversation = (INTEGRATION / "conversation.py").read_text()
    assert "DEFAULT_ROLLING_DAYS" in storage
    assert "timedelta(days=self.rolling_days)" in storage
    assert "is_sensitive(text)" in storage
    assert "recall_summary" in conversation
    assert "save_summary" in conversation
    assert "latest_summary" in conversation
    assert "list_memories(DEFAULT_MAX_RESULTS)" in conversation


def test_forget_and_dashboard_controls_are_local_and_scoped():
    init_source = (INTEGRATION / "__init__.py").read_text()
    conversation = (INTEGRATION / "conversation.py").read_text()
    button = (INTEGRATION / "button.py").read_text()
    sensor = (INTEGRATION / "sensor.py").read_text()
    assert 'SERVICE_FORGET = "forget"' in (INTEGRATION / "const.py").read_text()
    assert 'SERVICE_CLEAR = "clear"' in (INTEGRATION / "const.py").read_text()
    assert "clear_summaries" in conversation
    assert "forget_summaries" in conversation
    assert "async_call" not in init_source
    assert "async_call" not in button
    assert "item['text']" not in sensor
    assert "topic_counts" in sensor
