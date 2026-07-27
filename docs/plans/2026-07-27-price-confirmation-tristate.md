# Price Confirmation Three-State Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Distinguish known non-triggered execution conditions from genuinely
unknown evidence so screenshot/API analysis does not ask users for facts it can
already determine.

**Architecture:** Preserve `true`, `false`, and `null` through the strategy
context. Let the deterministic evaluator classify known negative or mismatched
confirmation as a non-triggered candidate, while retaining blocked status only
for unavailable evidence. Make clarification generation evidence-aware and
render both multimodal and structured results in the milestone audit.

**Tech Stack:** Python 3.10, Pydantic, FastAPI, Pytest, Next.js 15, React,
TypeScript, Playwright.

---

### Task 1: Lock the Three-State Contract

**Files:**
- Modify: `tests/strategy/test_context_builder.py`
- Modify: `tests/strategy/test_milestone_pipeline.py`
- Modify: `src/trading_agent/strategy/context.py`
- Modify: `src/trading_agent/strategy/context_builder.py`

**Step 1: Write the failing tests**

Add tests proving:

- a usable execution snapshot with no confirmation produces
  `price_confirmation is False`;
- no execution snapshot produces `price_confirmation is None`;
- a structured execution confirmation remains `True`.

**Step 2: Run the focused tests**

Run:

```sh
pytest -q tests/strategy/test_context_builder.py tests/strategy/test_milestone_pipeline.py
```

Expected: the new assertions fail because the context currently coerces
unknown confirmation to `False`.

**Step 3: Implement the minimal propagation change**

Change the context field and builder return path to preserve `None`. Do not
change market-data formulas or screenshot extraction.

**Step 4: Verify**

Run the same focused command and expect all tests to pass.

### Task 2: Separate Known Non-Trigger From Unknown Block

**Files:**
- Modify: `tests/strategy/test_milestone_pipeline.py`
- Modify: `src/trading_agent/strategy/price_confirmation.py`
- Modify: `src/trading_agent/domain/enums.py` only if a status enum is needed
- Modify: `src/trading_agent/decision/policy.py` if blocking-step handling needs
  to distinguish unknown evidence

**Step 1: Write the failing tests**

Add cases for:

- known `False` confirmation producing `CANDIDATE`, `NOT_TRIGGERED`, and no
  `PRICE_NOT_CONFIRMED`;
- known `True` with opposite direction producing `CANDIDATE` and
  `CONFIRMATION_DIRECTION_MISMATCH`;
- unknown confirmation producing `BLOCKED` and `PRICE_NOT_CONFIRMED`.

**Step 2: Run the focused test**

Run:

```sh
pytest -q tests/strategy/test_milestone_pipeline.py
```

Expected: known-negative cases fail because the evaluator currently returns
`BLOCKED`.

**Step 3: Implement the minimal evaluator change**

Use `CANDIDATE` for known non-triggered states and retain `BLOCKED` only when
the confirmation fact is `None`. Keep the existing strategy direction and type
checks unchanged.

**Step 4: Verify**

Run the focused strategy tests and expect all to pass.

### Task 3: Make Clarification Generation Evidence-Aware

**Files:**
- Modify: `tests/clarification/test_questions.py`
- Modify: `src/trading_agent/clarification/questions.py`

**Step 1: Write the failing tests**

Add analysis fixtures proving:

- `CONFIRMATION_DIRECTION_MISMATCH` creates no price-confirmation question;
- `PRICE_NOT_CONFIRMED` with a structured execution result creates no question;
- `PRICE_NOT_CONFIRMED` with no execution evidence still creates the question.

**Step 2: Run the focused tests**

Run:

```sh
pytest -q tests/clarification/test_questions.py
```

Expected: the first two new tests fail because blocker-to-question mapping is
currently unconditional.

**Step 3: Implement the evidence guard**

Inspect `evidence_set`, allowed usage, execution role, structured confirmation
fields, and screenshot strategy facts before adding `price_confirmation`.
Keep questions for genuine missing or unsupported evidence.

**Step 4: Verify**

Run the focused clarification tests and expect all to pass.

### Task 4: Render the Reason in the Audit UI

**Files:**
- Modify: `web/lib/api.ts`
- Modify: `web/components/milestone-card.tsx`
- Modify: `web/app/globals.css`
- Test: `web/tests/strategy-console.spec.ts`

**Step 1: Write the failing Playwright assertions**

Assert that a known direction mismatch displays “条件未触发” and the
observed/required directions, while a true unknown state displays the
clarification question instead.

**Step 2: Run the focused E2E test**

Run:

```sh
npx playwright test tests/strategy-console.spec.ts --project=desktop --grep "price confirmation"
```

Expected: the new assertions fail because the audit currently exposes only
generic blocker text.

**Step 3: Implement the minimal presentation change**

Expose the structured details already emitted by the backend and render them as
the adopted conclusion. Do not render hidden model reasoning.

**Step 4: Verify**

Run the focused E2E test on desktop and mobile.

### Task 5: Real CF2609 Regression and Full Gates

**Files:**
- Modify: `web/tests/api-server.mjs` only if the deterministic fixture needs
  the new tri-state payload.
- No unrelated production files.

**Step 1: Run all focused tests**

Run backend strategy and clarification tests plus the relevant Playwright
tests.

**Step 2: Run all quality gates**

```sh
pytest -q
ruff check .
mypy src
cd web
npm run lint
npm run build
npm run test:e2e
```

**Step 3: Reanalyze CF2609**

Restart the local runtime and submit a new idempotency key for the existing
case. Verify the latest analysis has:

- public data questions: zero;
- `price_confirmation` known from API or screenshot;
- no clarification for a known direction mismatch;
- final action and milestone status aligned.

**Step 4: Verify the live UI**

Open the case page at 1180px and confirm the audit displays the automatic
execution-period interpretation and no incorrect user-input request.
