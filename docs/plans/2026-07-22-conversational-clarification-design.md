# Conversational Clarification Design

## Goal

Turn strategy blockers caused by missing, ambiguous, or low-confidence screenshot
information into a focused conversation. The user supplies only the facts needed to
continue analysis. Confirmed answers become auditable evidence and trigger a
deterministic strategy re-evaluation without re-running vision extraction.

## Product Rules

1. The system identifies each uncertain field, explains why it is uncertain, names
   the blocked milestone, and asks one concrete question.
2. Users answer in natural language. The system converts the answer into proposed
   structured facts and shows its interpretation before applying it.
3. The user must explicitly confirm the interpreted facts.
4. Confirmed facts may fill missing, unknown, or low-confidence fields.
5. Confirmed facts do not silently overwrite clear screenshot evidence, structured
   market data, or hard risk constraints. Conflicts remain visible and blocked.
6. Every clarification stores the original message, interpreted facts, confirmation
   state, timestamp, and affected blockers.
7. Re-evaluation reuses the existing evidence set. It does not call the multimodal
   provider again.
8. The final decision and each milestone must show which changes came from user
   clarification.

## Recommended Interaction

The case page adds a clarification panel beside the eight-step ledger.

Each clarification card shows:

- uncertain field;
- current value;
- reason for uncertainty;
- affected milestone;
- concrete question;
- expected answer examples;
- whether user confirmation can resolve the blocker.

The user writes one conversational response covering one or more open questions.
The server parses it into a proposal. The UI responds with an interpretation such
as:

> I understand that the daily bar is closed, the 60-minute bar is closed, and CCYD
> shows long liquidation of 4,425. Please confirm or correct these facts.

The user can confirm the proposal or send a correction. Confirmation triggers
re-evaluation and redirects to the updated case result.

## Data Model

Clarifications are stored as case events instead of mutable analysis fields.

`CLARIFICATION_PROPOSED`

- clarification ID;
- source analysis ID;
- original user message;
- proposed structured facts;
- matched questions and blockers;
- parser provider/model;
- status `PENDING_CONFIRMATION`.

`CLARIFICATION_CONFIRMED`

- clarification ID;
- confirmed structured facts;
- confirmation timestamp;
- source message;
- affected blockers.

Case state exposes the ordered clarification history and the current confirmed
facts. Analysis payloads record which clarification IDs and fact evidence IDs were
used.

## Structured Facts

The first release supports fields that already exist in `StrategyContext`:

- `state_bar_closed`;
- `execution_bar_closed`;
- `position_behavior_state`;
- `open_interest_change`;
- `price_confirmation`;
- `price_confirmation_direction`;
- `price_confirmation_type`;
- `contract`;
- `timeframe`;
- `cutoff_time`.

Each fact includes:

- field name;
- typed value;
- confidence;
- provenance `user_confirmed`;
- source clarification ID;
- explanation.

## Clarification Generation

Question generation is deterministic. Known blocker codes map to supported fields
and Chinese questions. Free-text model blockers use keyword mapping where safe.
Unknown blockers remain visible but are marked as requiring a new screenshot or
structured market data rather than user confirmation.

Examples:

- `BAR_CLOSE_UNKNOWN` asks whether the daily bar is closed.
- `EXECUTION_CUTOFF_TIME_MISSING` asks for the exact 60-minute cutoff time.
- `OPEN_INTEREST_MISSING` asks for the visible open-interest value or change.
- `PRICE_NOT_CONFIRMED` asks for the closed execution-bar confirmation pattern.

## Parsing

The clarification parser accepts the user message, open questions, existing
evidence summary, and supported fact schema. Codex is primary. Its response must
validate against a strict Pydantic schema.

Parsing does not change case state. It only creates a proposal. Unsupported,
ambiguous, or contradictory values remain unresolved and generate a follow-up
question.

## Evidence Merge

On confirmation, user facts are converted into synthetic evidence observations.
They are appended to a copy of the latest evidence set with:

- stable evidence IDs;
- provenance `user_confirmed`;
- confidence `1.0`;
- the source clarification ID;
- no image path.

The merge only fills fields that are missing, unknown, unsupported, or explicitly
blocked. A clear conflicting visual or structured value produces
`USER_CLARIFICATION_CONFLICT` and keeps usage blocked.

## Re-evaluation

Confirmation performs:

1. load latest completed analysis;
2. validate the proposal is pending and belongs to that analysis;
3. append the confirmed clarification event;
4. merge confirmed facts into the existing evidence set;
5. rebuild `StrategyContext`;
6. run the deterministic eight-step workflow;
7. save a new analysis with a change report;
8. return the new analysis ID and decision.

No image upload or multimodal extraction occurs during this path.

## API

- `GET /v1/cases/{case_id}/clarifications`
  returns open questions and clarification history.
- `POST /v1/cases/{case_id}/clarifications`
  accepts a user message and returns an interpreted proposal.
- `POST /v1/cases/{case_id}/clarifications/{clarification_id}/confirm`
  confirms facts and returns the re-evaluated analysis.

All mutation endpoints require idempotency keys.

The web application exposes same-origin proxy routes so API tokens remain server
side.

## Error Handling

- stale proposal: `409`, ask the user to regenerate against the latest analysis;
- ambiguous answer: return proposal with unresolved questions, do not evaluate;
- unsupported field: keep blocker and explain required evidence type;
- conflicting answer: retain both sources and block the affected milestone;
- duplicate confirmation: return the cached re-evaluation result;
- provider failure during parsing: return recoverable `502/503`.

## Testing

Backend:

- blocker-to-question mapping;
- strict clarification parsing;
- proposal persistence and idempotency;
- confirmation audit events;
- user facts fill unknown fields;
- user facts cannot overwrite clear conflicting evidence;
- confirmation re-evaluates without invoking the vision provider;
- final decision aligns with changed milestones.

Frontend:

- blocked case shows concrete clarification cards;
- conversational message produces an interpretation preview;
- correction does not mutate analysis;
- confirmation creates a new analysis;
- changed milestones identify user-confirmed evidence;
- desktop and mobile layouts;
- error and stale-proposal recovery.

End to end:

- submit screenshots;
- receive blocked analysis;
- answer requested questions;
- confirm interpreted facts;
- observe updated eight-step ledger and final conclusion;
- verify no additional vision-provider call occurred.
