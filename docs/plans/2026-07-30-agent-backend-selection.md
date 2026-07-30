# Agent Backend and Model Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let each case select Codex or Kimi Code plus a model, with Kimi 3 as the Kimi default and one provider used consistently for vision, clarification, and follow-up conversation.

**Architecture:** Add a backend registry that exposes capability-aware manifests and resolves a case-pinned runtime bundle. Persist the selection in case events, route all model calls through the selected bundle, and expose Agent/model selectors in both the new-analysis composer and active conversation header. Kimi uses a bounded ACP stdio JSON-RPC client with denied tool permissions and original image content blocks.

**Tech Stack:** Python 3.10, FastAPI, Pydantic, SQLite event state, Agent Client Protocol over stdio, Next.js 15, React 19, TypeScript, pytest, Playwright.

---

### Task 1: Agent backend registry

**Files:**
- Create: `src/trading_agent/agents/models.py`
- Create: `src/trading_agent/agents/registry.py`
- Modify: `src/trading_agent/config.py`
- Modify: `.env.local.example`
- Modify: `src/trading_agent/local_runtime.py`
- Test: `tests/agents/test_agent_registry.py`
- Test: `tests/test_bootstrap.py`
- Test: `tests/deployment/test_local_runtime.py`

Write failing tests for Codex and Kimi manifests, Codex defaults, Kimi 3
defaults, model capability probing, disabled reasons, and legacy configuration.
Implement immutable model/backend manifests and a registry that resolves a
runtime bundle without silent fallback.

### Task 2: Kimi ACP providers

**Files:**
- Create: `src/trading_agent/providers/kimi_acp.py`
- Modify: `src/trading_agent/providers/factory.py`
- Test: `tests/providers/test_kimi_acp_provider.py`

Write failing tests for ACP initialization, denied permissions, Kimi 3 model
selection, original PNG image blocks, strict JSON parsing, clarification
boundaries, conversation immutability, timeouts, and unavailable models.
Implement one ACP transport adapter plus vision, clarification, and
conversation providers.

### Task 3: Persist selection and route analysis

**Files:**
- Modify: `src/trading_agent/db/repositories.py`
- Modify: `src/trading_agent/api/app.py`
- Modify: `src/trading_agent/workflows/activities.py`
- Modify: `src/trading_agent/workflows/analysis.py`
- Modify: `src/trading_agent/services/analysis.py`
- Test: `tests/api/test_agent_backend_flow.py`
- Test: `tests/workflows/test_temporal_worker.py`

Write failing tests for backend discovery, create-case selection, legacy Codex
fallback, exact model persistence, consistent follow-up and clarification
routing, switch events, full vision refresh, rollback on failure, idempotency,
and no automatic provider fallback. Implement the API and event-state changes.

### Task 4: Frontend Agent and model selection

**Files:**
- Create: `web/components/agent-selector.tsx`
- Modify: `web/components/analysis-input.tsx`
- Modify: `web/components/trading-chat.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/app/api/analysis/route.ts`
- Create: `web/app/api/agent-backends/route.ts`
- Create: `web/app/api/cases/[caseId]/agent-backend/route.ts`
- Modify: `web/tests/strategy-console.spec.ts`

Write failing Playwright assertions for new-case and conversation selectors,
Kimi 3 defaulting, disabled reasons, request payloads, dynamic progress text,
successful switching, and switch failure. Implement the accessible selectors
and server proxies.

### Task 5: Diagnostics, documentation, and verification

**Files:**
- Modify: `src/trading_agent/local_runtime.py`
- Modify: `docs/runbook.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Test: `tests/deployment/test_local_runtime.py`
- Test: `tests/deployment/test_readme.py`

Document Kimi 3 configuration without modifying global Kimi Code files. Add
doctor output for each backend/model. Run:

```sh
pytest -q
ruff check src tests
mypy
cd web && npm run lint && npm run build && npm run test:e2e
```

Run a real Kimi image smoke test only when `kimi-k3` is configured with
`image_in`; otherwise verify the UI and doctor show the exact unavailable
reason.
