"""Private, observe-only Home Context Memory integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SERVICE_CLEAR, SERVICE_FORGET
from .storage import MemoryStore

_STORE_KEY = "store"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML (not supported; configuration is UI-managed)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the selectable memory-only agent and private status controls."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.setdefault(_STORE_KEY, MemoryStore(hass))
    domain_data.setdefault("status_entities", [])

    async def async_forget(call) -> None:
        scope = call.data["scope"]
        query = call.data.get("query", "").strip()
        if scope == "memories":
            await store.forget(query) if query else await store.clear_memories()
        elif scope == "summaries":
            await store.forget_summaries(query) if query else await store.clear_summaries()
        else:
            await store.forget(query) if query else await store.clear_memories()
            await store.forget_summaries(query) if query else await store.clear_summaries()
        for entity in domain_data.get("status_entities", []):
            entity.async_schedule_update_ha_state(True)

    async def async_clear(call) -> None:
        scope = call.data["scope"]
        if scope in ("memories", "all"):
            await store.clear_memories()
        if scope in ("summaries", "all"):
            await store.clear_summaries()
        for entity in domain_data.get("status_entities", []):
            entity.async_schedule_update_ha_state(True)

    if not hass.services.has_service(DOMAIN, SERVICE_FORGET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORGET,
            async_forget,
            schema=vol.Schema({
                vol.Required("scope"): vol.In(["memories", "summaries", "all"]),
                vol.Optional("query", default=""): cv.string,
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR,
            async_clear,
            schema=vol.Schema({vol.Required("scope"): vol.In(["memories", "summaries", "all"])}),
        )

    await hass.config_entries.async_forward_entry_setups(entry, list(PLATFORMS))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the conversation agent and status controls."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, list(PLATFORMS))
    if unloaded:
        hass.services.async_remove(DOMAIN, SERVICE_FORGET)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR)
        hass.data.pop(DOMAIN, None)
    return unloaded
