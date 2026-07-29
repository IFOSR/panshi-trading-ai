# Conversation Permanent Deletion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add safe permanent deletion for individual and all conversation history.

**Architecture:** The backend owns permanent deletion and image cleanup. Next.js
provides same-origin authenticated proxies, while a shared client sidebar owns
confirmation, optimistic loading state, navigation, and error rendering.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL-compatible statements,
Next.js 15, React 19, Playwright, pytest.

---

### Task 1: Repository deletion

**Files:**
- Modify: `src/trading_agent/db/repositories.py`
- Test: `tests/db/test_repositories.py`

1. Add failing tests proving one case deletion removes its case, events,
   analyses, and idempotency records without affecting another case.
2. Run the focused tests and verify they fail because deletion methods do not
   exist.
3. Implement `delete_case()` and `delete_all_cases()` with SQLAlchemy delete
   statements ordered from dependent records to cases.
4. Run the focused tests and verify they pass.

### Task 2: Backend API and image cleanup

**Files:**
- Modify: `src/trading_agent/api/app.py`
- Test: `tests/api/test_case_flow.py`

1. Add failing tests for single deletion, repeated deletion, bulk deletion,
   removal of the case image directory, and restoration when database deletion
   fails.
2. Run the focused tests and verify the endpoints return 405.
3. Add safe image-directory quarantine helpers and the two DELETE endpoints.
4. Run the focused API tests and verify they pass.

### Task 3: Browser proxy routes

**Files:**
- Modify: `web/app/api/cases/route.ts`
- Create: `web/app/api/cases/[caseId]/route.ts`
- Test: `web/tests/strategy-console.spec.ts`
- Modify: `web/tests/api-server.mjs`

1. Add failing proxy tests for local-origin enforcement and upstream deletion.
2. Run the focused Playwright API tests and verify they fail.
3. Implement DELETE handlers using `trustedLocalOrigin`, `SAFE_ID`,
   `proxyConfiguration`, and `relayJson`.
4. Add deletion behavior to the API fixture and rerun the focused tests.

### Task 4: Sidebar deletion interface

**Files:**
- Modify: `web/components/conversation-sidebar.tsx`
- Modify: `web/app/globals.css`
- Test: `web/tests/strategy-console.spec.ts`

1. Add failing E2E tests for cancel, deleting a non-active row, deleting the
   active case, clear-all, and preserving rows on failure.
2. Run the focused tests and verify the controls do not exist.
3. Convert the sidebar to a client component, add accessible confirmation
   dialogs, loading/error state, router refresh, and active-case redirect.
4. Add intentional destructive-action styling and rerun the focused tests.

### Task 5: Full verification

1. Run `pytest -q`.
2. Run `ruff check .`.
3. Run `mypy src/trading_agent`.
4. Run `npx tsc --noEmit` and `npm run build` in `web`.
5. Run `npm run test:e2e` in `web`.
6. Run `git diff --check`.
7. Restart with `./trading-agent.sh restart` and verify port `8989`.
