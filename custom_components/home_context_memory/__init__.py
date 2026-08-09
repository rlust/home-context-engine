"""Private, observe-only Home Context Memory conversation agent."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORM


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML (not supported; configuration is UI-managed)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the selectable memory-only conversation agent."""
    await hass.config_entries.async_forward_entry_setups(entry, [PLATFORM])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the conversation agent."""
    return await hass.config_entries.async_unload_platforms(entry, [PLATFORM])
