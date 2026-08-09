"""Scoped, local-only memory clearing buttons."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN]["store"]
    status_entities = hass.data[DOMAIN]["status_entities"]
    async_add_entities([
        MemoryClearButton(store, status_entities, "summaries", "Forget session summaries", "mdi:message-badge-outline"),
        MemoryClearButton(store, status_entities, "memories", "Forget durable memories", "mdi:brain-off"),
    ])


class MemoryClearButton(ButtonEntity):
    """A deliberate dashboard control scoped to one local store collection."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, store, status_entities, scope: str, name: str, icon: str) -> None:
        self._store = store
        self._status_entities = status_entities
        self._scope = scope
        self._attr_name = name
        self._attr_unique_id = f"home_context_memory_clear_{scope}"
        self._attr_icon = icon

    async def async_press(self) -> None:
        if self._scope == "summaries":
            await self._store.clear_summaries()
        else:
            await self._store.clear_memories()
        for entity in self._status_entities:
            entity.async_schedule_update_ha_state(True)
