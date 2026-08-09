import ast
import json
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
