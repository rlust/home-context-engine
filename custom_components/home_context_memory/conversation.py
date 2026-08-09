"""Memory-only Assist conversation entity.

This agent answers memory commands and reports narrowly relevant saved context.
It deliberately has no Home Assistant service/tool calls and never delegates
ordinary requests to another agent.
"""

from __future__ import annotations

import re

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationEntity, ConversationEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.intent import IntentResponse
from .const import DEFAULT_MAX_RESULTS, DOMAIN
from .storage import MemoryStore


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([HomeContextMemoryConversationEntity(hass, entry)])


class HomeContextMemoryConversationEntity(ConversationEntity):
    """Selectable, observe-only memory conversation agent."""

    _attr_has_entity_name = True
    _attr_name = "Memory"
    _attr_supported_features = ConversationEntityFeature(0)
    _attr_supported_languages = ["*"]

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Home Context Memory"}
        self._memory = MemoryStore(hass)

    async def _async_handle_message(self, user_input, chat_log):
        text = user_input.text.strip()
        lowered = text.lower()
        if lowered.startswith(("remember that ", "remember ")):
            fact = re.sub(r"^remember(?: that)?\s+", "", text, flags=re.I)
            speech = ("Okay, I'll remember that." if await self._memory.save_memory(fact)
                      else "I won't save that because it may contain sensitive information.")
        elif lowered.startswith(("forget ", "delete memory ")):
            query = re.sub(r"^(?:forget|delete memory)\s+", "", text, flags=re.I)
            speech = f"I forgot {await self._memory.forget(query)} matching memory."
        elif lowered in {"recall", "what do you remember", "what do you remember?"}:
            items = await self._memory.list_memories(DEFAULT_MAX_RESULTS)
            summary = await self._memory.latest_summary()
            if not items and not summary:
                speech = "I don't have any saved memories yet."
            else:
                parts = ([f"Recent conversation: {summary['text']}"] if summary else [])
                parts.extend(f"- {item['text']}" for item in items)
                speech = "\n".join(parts)
        else:
            items = await self._memory.recall(text, DEFAULT_MAX_RESULTS)
            if items:
                speech = "Relevant saved memory:\n" + "\n".join(f"- {item['text']}" for item in items)
            else:
                speech = "I have no relevant saved memory for that request."

        response = IntentResponse(language=user_input.language)
        response.async_set_speech(speech[:600])
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id,
            continue_conversation=False,
        )
