# Conversational Clarification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an auditable dialogue that identifies uncertain strategy inputs, interprets user answers, requires confirmation, and re-runs the eight-step strategy without re-running screenshot analysis.

**Architecture:** Deterministic blocker-to-question mapping produces the conversation agenda. A Codex structured-text provider interprets natural-language answers into a strict proposal. Confirmed facts are appended as case events, merged into a copy of the latest evidence set under `user_confirmed` provenance, and passed through the existing deterministic strategy workflow to create a new analysis.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy event-sourced case state, Codex CLI structured output, Next.js 15 App Router, React 19, Playwright, pytest.

---

### Task 1: Clarification Domain Model And Question Generation

**Files:**
- Create: `src/trading_agent/clarification/models.py`
- Create: `src/trading_agent/clarification/questions.py`
- Test: `tests/clarification/test_questions.py`

**Step 1: Write failing tests**

Cover:

- daily close uncertainty maps to `state_bar_closed`;
- 60-minute close uncertainty maps to `execution_bar_closed`;
- `OPEN_INTEREST_MISSING` maps to `open_interest_change`;
- `PRICE_NOT_CONFIRMED` maps to the price-confirmation group;
- derived blockers such as `NO_ENABLED_STRATEGY` do not create duplicate questions;
- Chinese free-text blockers from the current CF2609 case map to concrete questions;
- duplicate blockers collapse to one question.

**Step 2: Run tests and verify RED**

Run:

```bash
.local/venv/bin/python -m pytest -q tests/clarification/test_questions.py
```

Expected: import failure because clarification modules do not exist.

**Step 3: Implement strict models and deterministic mapping**

Models:

- `ClarificationQuestion`
- `ClarificationFact`
- `ClarificationProposal`
- `ClarificationHistoryItem`
- supported field literal and typed validation

The question generator accepts the latest analysis payload and returns only
user-resolvable questions with milestone attribution and answer examples.

**Step 4: Run tests and verify GREEN**

Run the same pytest command. Expected: all pass.

### Task 2: Codex Clarification Interpreter

**Files:**
- Create: `src/trading_agent/providers/clarification.py`
- Create: `src/trading_agent/clarification/prompts.py`
- Modify: `src/trading_agent/providers/base.py`
- Test: `tests/providers/test_clarification_provider.py`

**Step 1: Write failing provider contract tests**

Cover:

- Codex command uses `gpt-5.6-sol`, strict schema, ephemeral isolated workspace,
  no images, and stdin prompt;
- valid JSON becomes a `ClarificationProposal`;
- invalid JSON raises `ProviderResponseError`;
- missing credentials or non-zero exit raises `ProviderUnavailable`;
- answers outside the open question set are rejected;
- ambiguous answers remain unresolved rather than being guessed.

**Step 2: Verify RED**

```bash
.local/venv/bin/python -m pytest -q tests/providers/test_clarification_provider.py
```

**Step 3: Implement interpreter**

Add a `ClarificationProvider` protocol and `ClarificationRequest`. Implement
`CodexClarificationProvider` using the same isolated Codex CLI security posture as
the vision provider. Render a prompt containing:

- original user message;
- open questions;
- latest evidence summary;
- supported fact schema;
- instruction to extract only explicitly supplied facts.

**Step 4: Verify GREEN**

Run the provider tests.

### Task 3: User-Confirmed Evidence Merge

**Files:**
- Create: `src/trading_agent/clarification/evidence.py`
- Modify: `src/trading_agent/strategy/context_builder.py`
- Test: `tests/clarification/test_evidence_merge.py`

**Step 1: Write failing merge tests**

Cover:

- user confirmation fills unknown daily close;
- user confirmation fills unknown execution close;
- open-interest change clears its missing blocker;
- position behavior and price confirmation gain support references;
- exact matching visual facts are accepted;
- clear conflicting visual or structured facts are not overwritten;
- conflicts add `USER_CLARIFICATION_CONFLICT`;
- generated observations carry `user_confirmed` provenance and clarification ID;
- unrelated blockers remain.

**Step 2: Verify RED**

```bash
.local/venv/bin/python -m pytest -q tests/clarification/test_evidence_merge.py
```

**Step 3: Implement minimal merge**

Clone the latest evidence set and apply only supported facts. Trust
`user_confirmed` fact provenance in `_fact_supported`. Remove only the exact
blockers associated with confirmed questions.

**Step 4: Verify GREEN**

Run merge and strategy-context tests.

### Task 4: Event-Sourced Clarification Persistence

**Files:**
- Modify: `src/trading_agent/db/repositories.py`
- Test: `tests/db/test_repositories.py`

**Step 1: Write failing repository tests**

Cover:

- `CLARIFICATION_PROPOSED` appends ordered history;
- `CLARIFICATION_CONFIRMED` updates the matching proposal;
- confirmed facts are exposed in case state;
- event replay reconstructs the same clarification state;
- existing analysis and action history remain unchanged.

**Step 2: Verify RED**

```bash
.local/venv/bin/python -m pytest -q tests/db/test_repositories.py -k clarification
```

**Step 3: Implement event application**

Extend `_apply_event` only. Keep proposals and confirmations immutable in the
event log.

**Step 4: Verify GREEN**

Run repository tests.

### Task 5: Clarification API And Re-evaluation

**Files:**
- Modify: `src/trading_agent/api/app.py`
- Create: `src/trading_agent/services/clarification.py`
- Test: `tests/api/test_clarification_flow.py`

**Step 1: Write failing API tests**

Cover:

- GET returns open questions for the latest analysis;
- POST message invokes the clarification provider and stores a pending proposal;
- POST is idempotent;
- proposal cannot mutate strategy output before confirmation;
- confirm writes an audit event and creates a new analysis;
- confirm reuses evidence and never invokes the vision provider;
- repeated confirm returns cached result;
- stale proposal returns `409`;
- provider response/unavailable errors return `502/503`;
- final decision and milestone evidence reference confirmed facts.

**Step 2: Verify RED**

```bash
.local/venv/bin/python -m pytest -q tests/api/test_clarification_flow.py
```

**Step 3: Implement API**

Add:

- `GET /v1/cases/{case_id}/clarifications`
- `POST /v1/cases/{case_id}/clarifications`
- `POST /v1/cases/{case_id}/clarifications/{clarification_id}/confirm`

Extract analysis payload construction into a shared helper so initial analysis and
clarification re-evaluation produce identical audit/change-report structures.

**Step 4: Verify GREEN**

Run clarification API tests and existing case-flow tests.

### Task 6: Web Data Mapping And Secure Proxy Routes

**Files:**
- Modify: `web/lib/api.ts`
- Create: `web/app/api/cases/[caseId]/clarifications/route.ts`
- Create: `web/app/api/cases/[caseId]/clarifications/[clarificationId]/confirm/route.ts`
- Test: `web/tests/strategy-console.spec.ts`

**Step 1: Add failing web API tests**

Cover:

- case view includes open questions and history;
- unsafe identifiers are rejected;
- proxy requires a same-origin local request;
- API credentials stay server-side;
- upstream `409`, `502`, and `503` details are preserved.

**Step 2: Verify RED**

```bash
cd web && npm run test:e2e -- --grep "clarification proxy"
```

**Step 3: Implement mappings and proxy routes**

Reuse the existing safe-ID and loopback-origin rules from the analysis route.

**Step 4: Verify GREEN**

Run targeted Playwright tests and TypeScript.

### Task 7: Clarification Conversation UI

**Files:**
- Create: `web/components/clarification-panel.tsx`
- Modify: `web/app/cases/[caseId]/page.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/lib/api.ts`
- Test: `web/tests/strategy-console.spec.ts`

**Step 1: Write failing UI tests**

Cover desktop and mobile:

- blocked case shows a clarification panel;
- each card states uncertain information, reason, affected step, and exact question;
- user message produces an interpretation preview;
- preview lists proposed facts and unresolved questions;
- no analysis changes before confirmation;
- confirmation refreshes the same case and shows a changed analysis;
- user-confirmed provenance appears in milestone evidence;
- correction can be submitted instead of confirmation;
- no questions state is clear and does not show an empty composer.

**Step 2: Verify RED**

```bash
cd web && npm run test:e2e -- --grep "clarification"
```

**Step 3: Implement UI**

Place the panel after the change report and before the ledger. Use a strong
editorial conversation layout, not a generic chat bubble clone. Keep the existing
paper, ink, red, green, and amber visual language.

**Step 4: Verify GREEN**

Run targeted desktop and mobile Playwright tests.

### Task 8: Full Regression, Production Build, And Real-Case Check

**Files:**
- Modify only if verification finds a defect.

**Step 1: Run backend quality gates**

```bash
.local/venv/bin/python -m pytest -q
/Users/ylfego/anaconda3/bin/ruff check src tests evals
.local/venv/bin/python -m mypy src/trading_agent
```

Expected: all pass.

**Step 2: Run frontend quality gates**

```bash
cd web
npm run lint
npm run test:e2e
```

Expected: all pass with only the intentional oversized-request mobile skip.

**Step 3: Build and restart local production**

```bash
./trading-agent.sh stop
cd web && npm run build
cd .. && ./trading-agent.sh start
```

**Step 4: Verify the CF2609 case**

Check `http://127.0.0.1:8989/cases/4ed65e78-8c68-515f-9078-00c1d0ececd9`:

- clarification panel identifies the daily close, 60-minute close, CCYD/open
  interest, and price-confirmation gaps;
- submitting and confirming a clarification creates a new analysis;
- the vision provider call count does not increase;
- eight milestones and final action remain aligned;
- confirmed facts show `user_confirmed` provenance;
- unresolved hard blockers remain visible.
