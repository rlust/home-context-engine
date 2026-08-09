"""Config flow for Home Context Memory."""

from __future__ import annotations

from homeassistant import config_entries
from .const import DOMAIN


class HomeContextMemoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one local memory agent entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Show the one-click setup flow."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Home Context Memory", data={})
        return self.async_show_form(step_id="user")


async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    """Return an empty options flow; retention/privacy are fixed safeguards."""
    return HomeContextMemoryOptionsFlow()


class HomeContextMemoryOptionsFlow(config_entries.OptionsFlow):
    """Keep safeguards non-configurable during the trial."""

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="init")
