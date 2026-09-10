"""Read-only, request-scoped topology from Home Assistant registries."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace


def select_topology(query, entities, devices, areas, floors):
    """Only include explicitly exposed, named matches; never infer occupancy."""
    words = tuple(re.findall(r"\w+", query.casefold()))
    result = []
    size = 0
    for entry in sorted(entities, key=lambda item: item.entity_id):
        if entry.disabled_by or entry.hidden_by or entry.entity_category:
            continue
        if entry.options.get("conversation", {}).get("should_expose") is not True:
            continue
        device = devices.get(entry.device_id) if entry.device_id else None
        area_id = entry.area_id or (device.area_id if device else None)
        area = areas.get(area_id) if area_id else None
        floor = floors.get(area.floor_id) if area and area.floor_id else None
        # HA's computed-name sentinel is not a string or a usable prompt label.
        name = next((value for value in (entry.name, entry.original_name, entry.entity_id)
                     if isinstance(value, str) and value.strip()), entry.entity_id)
        names = [name, *(entry.aliases or ())]
        if area:
            names.append(area.name)
        if floor:
            names.append(floor.name)
        matched = False
        for label in names:
            if not isinstance(label, str):
                continue
            tokens = tuple(re.findall(r"\w+", label.casefold()))
            if tokens and any(words[i:i + len(tokens)] == tokens for i in range(len(words))):
                matched = True
                break
        if not matched:
            continue
        record = {"entity": entry.entity_id, "name": name[:80],
                  "room": area.name[:80] if area else "unassigned",
                  "floor": floor.name[:80] if floor else "unassigned"}
        length = len(json.dumps(record, ensure_ascii=True)) + 1
        if size + length > 650:
            continue
        result.append(record)
        size += length
        if len(result) == 5:
            break
    return result


def read_topology(hass, query):
    """Use current in-memory registries, without remote scans or exposure writes."""
    from homeassistant.helpers import area_registry, device_registry, entity_registry, floor_registry

    return select_topology(
        query,
        entity_registry.async_get(hass).entities.values(),
        SimpleNamespace(get=device_registry.async_get(hass).async_get),
        SimpleNamespace(get=area_registry.async_get(hass).async_get_area),
        SimpleNamespace(get=floor_registry.async_get(hass).async_get_floor),
    )
