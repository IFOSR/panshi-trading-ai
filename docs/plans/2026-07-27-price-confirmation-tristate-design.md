# Price Confirmation Three-State Design

## Goal

Make screenshot and public market data authoritative for execution-period
confirmation, and ask the user only when the system genuinely cannot determine
the fact.

## Root Cause

The execution-period confirmation fact is semantically three-valued:

- `true`: a valid confirmation was identified.
- `false`: the execution period was available and no valid confirmation was
  identified, or the identified direction does not match the enabled strategy.
- `null`: the execution period or required confirmation evidence is unavailable
  or cannot be interpreted.

The current pipeline collapses this into a boolean. The clarification layer then
maps `PRICE_NOT_CONFIRMED` directly to a user question, even when the image or
structured 60-minute market data already proves that confirmation is absent or
directionally mismatched.

## Design

### Evidence Order

1. Codex multimodal extraction reads the original screenshot and records visible
   execution-period facts with provenance.
2. The market resolver fetches the matching public 60-minute bars and computes
   confirmation deterministically.
3. The merger keeps both sources, preferring structured values for exact
   timestamps, close state, and formula-derived confirmation.
4. If either source gives a definitive `true` or `false`, the result is known.
   A user question is allowed only when both sources remain unknown or the
   required source is unavailable.

### Strategy Semantics

- `CONFIRMED`: confirmation is known and matches the enabled strategy.
- `CANDIDATE` with `NOT_TRIGGERED`: evidence is complete, but confirmation is
  absent, directionally mismatched, or the setup is otherwise not ready.
- `BLOCKED` with `EVIDENCE_UNAVAILABLE`: required evidence is unknown and no
  automatic source can resolve it.

`PRICE_NOT_CONFIRMED` remains a data-unknown blocker only for the third case.
`CONFIRMATION_DIRECTION_MISMATCH` and `CONFIRMATION_TYPE_MISMATCH` are strategy
outcomes, not user clarification triggers.

### Clarification Rules

The clarification question generator must inspect the evidence and the
blocker type. It may generate `price_confirmation` only when:

- execution evidence is missing or untrusted;
- the market resolver did not provide a usable execution snapshot; and
- no definitive screenshot fact exists.

It must not generate a question for a definitive false result, a known
direction mismatch, or a known confirmation-type mismatch.

### UI

The milestone audit must show:

- screenshot interpretation;
- structured API result;
- final adopted result;
- the exact reason for `NOT_TRIGGERED` or `EVIDENCE_UNAVAILABLE`.

The user-facing copy must say “条件未触发” for a known negative result and
reserve “需要补充信息” for unknown evidence.

## Acceptance Criteria

- A complete 60-minute API result with no confirmation creates no user
  question.
- A bullish 60-minute confirmation while a short strategy is required is shown
  as a known direction mismatch and creates no user question.
- Missing execution evidence with no usable API result still creates the
  existing targeted clarification question.
- `CF2609` completes with zero public-data clarification questions and a
  deterministic final conclusion.
- Existing data blockers, privacy blockers, and API failures remain blocking.

## Test Strategy

- Unit tests for three-state context propagation.
- Strategy tests for known negative, direction mismatch, and unknown evidence.
- Clarification tests proving only unknown evidence creates questions.
- API and Playwright tests covering the real case view and visible copy.
- Full backend, frontend, build, lint, type, and live-case verification.
