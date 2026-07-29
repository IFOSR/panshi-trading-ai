# Screenshot-First Input Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the daily screenshot the only required market input while preserving optional account-private context and conservative risk defaults.

**Architecture:** Relax the Next.js proxy validation, skip structured position updates when the user selects automatic inference, and keep deterministic risk defaults server-side. Reshape the existing form without changing the backend analysis pipeline.

**Tech Stack:** Next.js 15, React 19, TypeScript, Playwright, FastAPI.

---

### Task 1: Proxy Defaults

**Files:**
- Modify: `web/app/api/analysis/route.ts`
- Test: `web/tests/strategy-console.spec.ts`

1. Add a failing request test that submits only privacy confirmation and a daily image.
2. Verify the request currently fails on contract/message/risk.
3. Make contract and message optional, default the message, and default risk values.
4. Add an `AUTO` position mode that skips the position update.
5. Verify the minimal request and existing validation tests pass.

### Task 2: Screenshot-First Form

**Files:**
- Modify: `web/components/analysis-input.tsx`
- Modify: `web/app/globals.css`
- Test: `web/tests/strategy-console.spec.ts`

1. Add failing UI assertions for the one-required-input message and screenshot checklist.
2. Make contract and message optional.
3. Default position to automatic inference.
4. Collapse position and risk controls as advanced overrides.
5. Explain which screenshot regions must remain visible and which facts are
   automatically fetched.
6. Verify desktop and mobile behavior.

### Task 3: Full Verification

**Files:**
- No production changes expected.

1. Run TypeScript, production build, and Playwright.
2. Run the backend test suite, Ruff, and Mypy.
3. Restart local services.
4. Create a fresh CF2609 case using the existing original screenshot and only
   the private position sentence.
5. Verify Codex extraction, public daily/60-minute evidence, all eight
   milestones, final action alignment, and zero public-data clarifications.
