import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

path = Path(__file__).parents[1] / "custom_components/home_context_memory/topology.py"
spec = importlib.util.spec_from_file_location("topology", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def entry(**changes):
    values = dict(entity_id="light.desk", name="Desk", original_name=None,
                  aliases=set(), area_id="office", device_id="device",
                  disabled_by=None, hidden_by=None, entity_category=None,
                  options={"conversation": {"should_expose": True}})
    values.update(changes)
    return NS(**values)


def select(query, entries):
    return module.select_topology(query, entries,
        {"device": NS(area_id="kitchen")},
        {"office": NS(name="Office", floor_id="up"),
         "kitchen": NS(name="Kitchen", floor_id=None)},
        {"up": NS(name="Second floor")})


def test_entity_area_precedes_device_area_and_floor_matches():
    assert select("Second floor lights", [entry()])[0]["room"] == "Office"
    assert select("kitchen lights", [entry()]) == []


def test_device_fallback_and_unassigned_are_explicit():
    assert select("Kitchen", [entry(area_id=None)])[0]["floor"] == "unassigned"
    assert select("Desk", [entry(area_id=None, device_id=None)])[0]["room"] == "unassigned"


def test_exposure_fails_closed_and_excludes_hidden_diagnostic_disabled():
    for change in [dict(options={}), dict(options={"conversation": {"should_expose": False}}),
                   dict(hidden_by="user"), dict(disabled_by="user"),
                   dict(entity_category="diagnostic")]:
        assert select("Office", [entry(**change)]) == []


def test_unrelated_query_and_partial_name_do_not_match():
    assert select("weather", [entry()]) == []
    assert select("officer", [entry()]) == []
    assert select("study lights", [entry(aliases={"Study"})])


def test_result_is_bounded_and_deterministic():
    entries = [entry(entity_id=f"light.desk_{i}") for i in range(100)]
    result = select("Office", entries)
    assert result == select("Office", list(reversed(entries)))
    assert len(result) <= 5
    assert sum(len(json.dumps(item)) + 1 for item in result) <= 650


def test_computed_name_sentinel_falls_back_to_text():
    sentinel = object()
    assert select("Office", [entry(name=sentinel, original_name="Desk")])[0]["name"] == "Desk"
    result = select("Office", [entry(name=sentinel, original_name=sentinel, aliases={sentinel})])
    assert result[0]["name"] == "light.desk"


def test_registry_adapter_uses_domain_specific_lookup_methods(monkeypatch):
    registries = dict(
        entity_registry=NS(entities={"light.desk": entry(name=object())}),
        device_registry=NS(async_get=lambda key: NS(area_id="office")),
        area_registry=NS(async_get_area=lambda key: NS(name="Office", floor_id="up")),
        floor_registry=NS(async_get_floor=lambda key: NS(name="Second floor")),
    )
    helpers = NS(**{name: NS(async_get=lambda hass, registry=registry: registry)
                    for name, registry in registries.items()})
    monkeypatch.setitem(sys.modules, "homeassistant", NS(helpers=helpers))
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    result = module.read_topology(NS(), "Office")
    assert result[0]["floor"] == "Second floor"
    assert result[0]["name"] == "light.desk"
