# Single Strategy Dropdown Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the native strategy select with an accessible custom dropdown that opens even when only one strategy is registered.

**Architecture:** Keep strategy discovery and switching APIs unchanged. Implement all dropdown state, keyboard behavior, selection rollback, and rendering inside the shared `StrategySelector` client component so the home and case pages inherit identical behavior.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS, Playwright.

---

### Task 1: Single-strategy expansion contract

**Files:**
- Modify: `web/tests/strategy-console.spec.ts`
- Modify: `web/tests/api-server.mjs`

**Step 1: Write the failing test**

Add a Playwright test that loads the real single-strategy fixture, clicks the strategy
trigger, and asserts that a `listbox` with one selected option becomes visible.

**Step 2: Run test to verify it fails**

Run:

```bash
cd web
npx playwright test -g "opens the strategy list with one registered strategy"
```

Expected: FAIL because the native select does not expose the required custom listbox.

### Task 2: Custom accessible dropdown

**Files:**
- Modify: `web/components/strategy-selector.tsx`
- Modify: `web/app/globals.css`

**Step 1: Implement minimal component**

Replace the native `select` with:

- A button carrying `aria-haspopup="listbox"` and `aria-expanded`.
- A conditionally rendered `role="listbox"`.
- One `role="option"` per strategy with `aria-selected`.
- Outside-click and Escape handling.
- Current-option selection that closes without calling the API.
- Different-option selection that preserves the existing strategy switch request.

**Step 2: Run focused test**

Run:

```bash
cd web
npx playwright test -g "opens the strategy list with one registered strategy"
```

Expected: PASS.

### Task 3: Regression and keyboard coverage

**Files:**
- Modify: `web/tests/strategy-console.spec.ts`

**Step 1: Add failing tests**

Cover:

- Escape closes the list.
- Choosing the current single option does not create a new analysis.
- Existing multi-strategy selection still switches strategy.

**Step 2: Implement only missing keyboard/focus behavior**

Keep all behavior in `StrategySelector`; do not add page-specific conditionals.

**Step 3: Run verification**

```bash
cd web
npx tsc --noEmit
npm run build
npm run test:e2e
cd ..
.local/venv/bin/pytest -q
ruff check .
.local/venv/bin/mypy src/trading_agent
git diff --check
./trading-agent.sh restart
./bin/trading-agent-local status
```

Expected: all checks pass and the web service remains available at
`http://127.0.0.1:8989`.
