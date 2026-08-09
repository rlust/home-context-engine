"""Privacy-preserving Home Context Memory status sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN]["store"]
    entities = [
        MemoryStatusSensor(store, "memory_count", "Durable memory count", "mdi:brain"),
        MemoryStatusSensor(store, "summary_count", "Session summary count", "mdi:message-text-clock"),
        MemoryStatusSensor(store, "summary_expires_at", "Session continuity expiry", "mdi:calendar-clock"),
        MemoryStatusSensor(store, "last_action", "Last memory audit action", "mdi:history"),
    ]
    hass.data[DOMAIN]["status_entities"].extend(entities)
    async_add_entities(entities)


class MemoryStatusSensor(SensorEntity):
    """Expose metadata only; never expose memory or summary text."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, store, key: str, name: str, icon: str) -> None:
        self._store = store
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"home_context_memory_{key}"
        self._attr_icon = icon

    async def async_update(self) -> None:
        status = await self._store.status()
        if self._key == "memory_count":
            self._attr_native_value = status["memory_count"]
        elif self._key == "summary_count":
            self._attr_native_value = status["summary_count"]
        elif self._key == "summary_expires_at":
            self._attr_native_value = status["summary_expires_at"] or "none"
        else:
            action = status["last_action"]
            self._attr_native_value = action["action"] if action else "none"
        self._attr_extra_state_attributes = {
            "topic_counts": status["topic_counts"],
            "last_action_scope": (status["last_action"] or {}).get("scope"),
            "last_action_at": (status["last_action"] or {}).get("at"),
        }
