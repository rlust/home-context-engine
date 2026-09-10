import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

_MODULE = Path(__file__).parents[1] / "custom_components/home_context_memory/context_brief.py"
_SPEC = importlib.util.spec_from_file_location("context_brief", _MODULE)
assert _SPEC and _SPEC.loader
_LOADED = importlib.util.module_from_spec(_SPEC)
sys.modules["context_brief"] = _LOADED
_SPEC.loader.exec_module(_LOADED)
build_context_brief = _LOADED.build_context_brief
selected_categories = _LOADED.selected_categories


def hass_with_states(values):
    return SimpleNamespace(
        states=SimpleNamespace(
            get=lambda entity_id: SimpleNamespace(state=values[entity_id])
            if entity_id in values
            else None
        )
    )


def test_selection_is_narrow_for_media_request():
    categories = selected_categories("what is playing in the media room")
    assert "media_state" in categories
    assert "door_summary" not in categories
    assert "presence_summary" not in categories


def test_brief_includes_only_selected_live_state_and_relevant_memory():
    hass = hass_with_states({"media_player.assist_master": "playing"})
    brief = build_context_brief(hass, "what is playing", [{"text": "I prefer jazz"}], None)
    assert "Media State: playing" in brief.text
    assert "I prefer jazz" in brief.text
    assert "Door Summary" not in brief.text
    assert brief.memory_count == 1
    assert "media_state" in brief.categories
    assert "relevant_memory" in brief.categories


def test_brief_is_bounded_and_does_not_call_services():
    hass = hass_with_states({"sensor.home_active_room": "Office"})
    brief = build_context_brief(hass, "room", [{"text": "x" * 1000}], None)
    assert len(brief.text) <= 1400
    assert "async_call" not in brief.text


def test_full_safety_policy_survives_overflow():
    hass = hass_with_states({entity: "x" * 120 for entity in _LOADED.CONTEXT_ENTITIES.values()})
    brief = build_context_brief(hass, "room home why door media health control",
        [{"text": "x" * 180}] * 3, {"text": "x" * 180},
        [{"entity": "light.desk", "room": "Office"}])
    assert len(brief.text) <= 1400
    assert brief.text.endswith("Missing context is not evidence of absence.")
    assert "Keep normal Assist confirmation and Home Assistant safety behavior." in brief.text


def test_topology_is_labeled_data_not_occupancy():
    brief = build_context_brief(hass_with_states({}), "Office", [], None,
        [{"entity": "light.desk", "room": "Office"}])
    assert "room_topology" in brief.categories
    assert "not proof of occupancy" in brief.text
