# Home Context Memory

Private, local Home Assistant conversation agents for the Home Context Engine
trial. The original Memory agent remains memory-only. A separate combined
agent, **Memory + ChatGPT Control**, delegates ordinary requests to the existing
`conversation.chatgpt_new` agent through Home Assistant's supported conversation
API after adding a bounded, request-scoped context brief.

## HACS installation

Add the private GitHub repository `rlust/home-context-engine` as a custom HACS
repository of type **Integration**, then download it. HACS expects exactly one
integration under `custom_components/home_context_memory/`.

Restart Home Assistant, then add **Home Context Memory** from Settings →
Devices & services. In the Assist pipeline editor, select the resulting
**Home Context Memory** conversation agent as a separate trial pipeline. Do not
replace the existing Chat GPT New pipeline unless explicitly chosen by the
user.

## Safety and storage

The memory-only agent never calls Home Assistant services or exposes LLM tools.
The combined agent adds no custom service/device calls, but intentionally retains
the full configured control capability of Chat GPT New, including its normal
Home Assistant confirmations and the existing `ai_actions_enabled` gate. Select
it only as a separate trial pipeline; it does not replace Chat GPT New.

Facts and short summaries are persisted through Home Assistant's `Store`
helper under `.storage`; the integration never edits `.storage` directly.
Summaries expire after 30 days. Sensitive-looking credentials, tokens,
account/payment numbers, and SSNs are refused. The store is local to this HA
instance and is not uploaded by this integration.

Each Assist turn creates a short, deterministic, sensitivity-filtered local
session topic. Related requests can retrieve one relevant topic, but the agent
does not dump prior conversation history. `forget that` clears session summaries
when no specific subject follows; `forget that <subject>` removes matching
durable memories and summaries. Explicit dashboard buttons provide separate,
deliberate clears for summaries and durable memories.

The integration also exposes metadata-only diagnostic entities: durable-memory
count, session-summary count, summary expiry, last audit action, whether a
ChatGPT brief was supplied, and broad context categories. They expose counts,
timestamps, topic/category labels, and scopes—not saved text. The combined agent
reads only exact selected Home Context entities whose category matches the
current request, plus relevant saved memory/session continuity. It does not send
full device inventories or persistent audit history from this integration.

### Newark dashboard

The companion `Home Context Memory` dashboard is admin-only and separate from
the existing Home Context dashboard. It shows the metadata-only status entities
and provides two scoped local clear buttons. It never controls lights, devices,
automations, or the preferred Assist pipeline.

The existing Home Context Observer and `input_boolean.ai_actions_enabled` are
unmodified. This package provides selectable side-by-side memory-only and
Home Context + ChatGPT Control trials, not a replacement for the preferred Chat
GPT New pipeline.
