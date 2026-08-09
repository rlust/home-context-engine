# Home Context Memory

Private, local, observe-only Home Assistant conversation agent for the Home
Context Engine trial.

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

The agent never calls Home Assistant services, exposes no LLM tools, changes no
entity, and does not delegate ordinary requests to another conversation agent.
It supports explicit `remember`, `recall`, and `forget` language only. Other
requests return relevant saved memory or a no-match response.

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
count, session-summary count, summary expiry, and last audit action. They expose
counts, timestamps, broad topic labels, and scopes—not saved text. Optional
read-only Home Context mode/activity helpers are used only as local context
hints when creating a session topic; no Home Assistant service is called.

### Newark dashboard

The companion `Home Context Memory` dashboard is admin-only and separate from
the existing Home Context dashboard. It shows the metadata-only status entities
and provides two scoped local clear buttons. It never controls lights, devices,
automations, or the preferred Assist pipeline.

The existing Home Context Observer and `input_boolean.ai_actions_enabled` are
unmodified. This package is a selectable memory-only trial, not a replacement
for the preferred Chat GPT New pipeline.
