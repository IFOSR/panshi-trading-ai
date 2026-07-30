# Agent Backend and Model Selection Design

## Goal

Allow each trading conversation to select one complete AI backend and model.
The selection covers original-image extraction, clarification interpretation,
and follow-up explanation.

## Product Behavior

The new-case composer and active conversation header expose two selectors:

- Agent: `Codex` or `Kimi Code`;
- Model: models supported by the selected Agent.

Defaults:

- Agent: `Codex`;
- Codex model: `gpt-5.6-sol`;
- Kimi Code model: `kimi-k3`.

Kimi Code also lists `kimi-code/kimi-for-coding`. A model that does not expose
image capability remains visible but disabled with a concrete reason.

The selected Agent and model are pinned to the case. Switching either value on
an existing case records an immutable system event and, when screenshots
exist, performs a full original-image reanalysis. Existing conclusions remain
unchanged and the new result becomes a new analysis version.

There is no silent provider fallback. If the selected Agent becomes
unavailable, the user sees the reason and can explicitly switch to another
Agent.

## Backend Architecture

Introduce an Agent Backend Registry. Each backend manifest contains:

- stable backend ID;
- display name;
- default model ID;
- model manifests;
- capabilities: vision, clarification, and conversation;
- current availability and an unavailable reason.

Each backend runtime bundles three provider contracts:

- `VisionProvider`;
- `ClarificationProvider`;
- `ConversationProvider`.

Codex reuses the current implementations. Kimi Code gains clarification and
conversation adapters and a non-interactive ACP client for image prompts.
Kimi image inputs use ACP image content blocks with the original bytes. Images
are not converted to video and no OpenCV or local OCR path is introduced.

The Kimi runtime uses an isolated working directory, empty skills, bounded
timeouts, and denies tool permission requests. It reads the user's existing
Kimi Code configuration but does not rewrite the global configuration.

## Kimi Model Availability

`kimi-k3` is the Kimi default model. Availability requires:

- executable `kimi`;
- a configured `kimi-k3` model alias;
- `image_in` capability;
- valid Kimi Code authentication;
- successful ACP initialization.

`kimi-code/kimi-for-coding` remains available only when its declared
capabilities include `image_in`. The current machine declares only `video_in`
and `tool_use`, so the UI must explain that it cannot serve screenshot
analysis.

The local runtime doctor reports each backend and model independently. Codex
remains usable when Kimi is unavailable, and Kimi configuration is not a
startup requirement.

## Persistence and API

Case state gains:

```json
{
  "agent_backend": {
    "backend_id": "codex",
    "model_id": "gpt-5.6-sol",
    "display_name": "Codex"
  }
}
```

Legacy cases without this field resolve to Codex and the configured Codex
model.

API additions:

- `GET /v1/agent-backends`: list manifests, models, capabilities, availability,
  and reasons;
- create-case fields `agent_backend_id` and `agent_model_id`;
- `POST /v1/cases/{case_id}/agent-backend`: select a backend/model and trigger
  reanalysis when required.

Analysis commands and persisted analysis payloads include the exact backend and
model. Conversation and clarification responses already record provider and
model; they must use the case-pinned runtime.

## Frontend

The new-case form places Agent and model selectors next to the strategy
selector. The conversation header uses the same accessible custom-selector
pattern.

The UI:

- always shows both Agents;
- disables unavailable models rather than hiding them;
- displays the unavailable reason;
- defaults Kimi to Kimi 3;
- shows a confirmation state while switching;
- appends a system message after a successful switch;
- refreshes the conversation after the new analysis completes.

Progress text uses the selected Agent name rather than hard-coded `Codex`.

## Error Handling

- invalid backend/model: `400`;
- configured but unavailable backend/model: `503` with a stable reason;
- switch during another case mutation: existing idempotency and conflict rules;
- failed reanalysis: selection is not committed, so the previous backend
  remains active;
- invalid Kimi output: `502`, with no fallback to Codex.

## Verification

TDD covers:

- registry manifests and default models;
- Kimi 3 availability probing;
- ACP image content construction and strict output validation;
- Kimi clarification and conversation adapters;
- create-case persistence and legacy fallback;
- backend/model switching with full reanalysis;
- no silent fallback;
- frontend Agent/model selection and disabled reasons;
- progress text using the selected Agent;
- end-to-end Codex and fake-Kimi conversation flows;
- local runtime doctor behavior.

Real Kimi image execution is conditional on a configured image-capable
`kimi-k3` alias and authentication. The regular suite uses deterministic ACP
fakes and never requires external model calls.
