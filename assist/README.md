# Assist conversational-memory trial

This is a local, private, observe-only trial component. It extends the Home
Context Engine without changing its observer, helpers, `ai_actions_enabled`
gate, or any device. The repository is a sanitized reference export, so this
directory is deliberately an adapter/service prototype rather than a live HA
configuration.

## Behavior

- Durable memory is saved only after an explicit `remember ...` command.
- Plain-language `recall` / `what do you remember` returns only relevant saved
  facts plus the latest rolling session summary; it never dumps chat history.
- `forget <topic>` removes matching durable facts and writes an audit event.
- Session summaries are local, replaceable per session, and expire after 30 days.
- Sensitive-looking content (credentials, tokens, payment/account numbers, and
  SSNs) is declined by default.
- Data is a JSON file plus an append-only JSONL audit file. Keep both on a
  private local filesystem with restrictive permissions in a real trial.

## Assist connection boundary

`adapter.py` is the integration-neutral boundary for a custom conversation
agent. It passes the utterance to `MemoryService.handle()` for memory-intent
phrases. A `command_response` is spoken directly; otherwise `context` contains
only narrowly matched saved facts, capped at 600 characters. The custom agent
can add that context to its own model prompt and then continue normal Assist
processing. The adapter must not pass raw transcripts or Home Assistant entity
state to this service, and must not call device services. Summary creation
should happen at session end from a sanitized, short text supplied by the
agent.

Home Assistant's Assist Pipeline selects STT, conversation engine, and TTS; it
does not provide a configuration field for an arbitrary memory/context
provider. Home Assistant does support custom conversation agents, whose message
handler receives the user input and chat log. Therefore this package is
ready-to-wire as part of a custom conversation integration, but it is not a
drop-in change to the existing `Chat GPT New` or other pipeline. The remaining
external step is to install/register a reviewed custom conversation agent in
the live HA config and restart/reload it according to that integration's
lifecycle. That step is intentionally not performed here.

Recommended manual trial:

1. Run the tests locally.
2. Use a temporary local store outside Home Assistant's config directory.
3. Say `Remember that I prefer jazz`, then ask `What do you remember about music?`.
4. Confirm an unrelated question gets no memory context.
5. Say `Forget jazz` and confirm it is gone; inspect the audit file.
6. Try a password/token utterance and confirm it is declined.
7. Keep the Home Context Observer unchanged and leave `ai_actions_enabled` off.

The live Newark inspection on 2026-08-09 found 11 Assist pipelines, with
`Chat GPT New` preferred. The existing pipeline surface can select
`conversation.chatgpt_new`, but cannot attach this adapter. The repository also
contains no live HA configuration directory, so no installation manifest or
restart command is assumed here.

This trial intentionally does not deploy, register an Assist pipeline, or write
to Home Assistant.
