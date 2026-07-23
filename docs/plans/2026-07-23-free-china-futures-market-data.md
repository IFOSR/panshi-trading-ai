# Free China Futures Market Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a free TqSdk-primary, AkShare-fallback China-futures data pipeline that fills screenshot gaps and feeds auditable structured evidence into the existing eight-step strategy.

**Architecture:** Add provider adapters behind the existing `MarketDataResolver` contract. Normalize provider data into `MarketDataSnapshot`, apply best-effort exchange validation, and keep all indicator and strategy calculations deterministic in the existing code. Local mode enables the free resolver by default and uses an optional backend Tq account without adding product login.

**Tech Stack:** Python 3.10+, Pydantic v2, TqSdk 3.10, AkShare 1.18, pandas, pytest, FastAPI.

---

### Task 1: Extend the Market Data Contract

**Files:**
- Modify: `src/trading_agent/market/resolver.py`
- Modify: `src/trading_agent/domain/evidence.py`
- Modify: `src/trading_agent/vision/evidence_merger.py`
- Modify: `src/trading_agent/strategy/context.py`
- Modify: `src/trading_agent/strategy/context_builder.py`
- Modify: `src/trading_agent/strategy/data_validity.py`
- Test: `tests/market/test_market_resolver.py`
- Test: `tests/strategy/test_context_builder.py`

**Steps:**

1. Write failing tests for snapshot sources, validation sources, quality issues,
   and step-1 audit details.
2. Run the focused tests and verify they fail because the fields do not exist.
3. Add the minimal typed fields and evidence merge behavior.
4. Run the focused tests and verify they pass.

### Task 2: Add Provider-Neutral Resolution

**Files:**
- Create: `src/trading_agent/market/providers/__init__.py`
- Create: `src/trading_agent/market/providers/base.py`
- Create: `src/trading_agent/market/providers/composite.py`
- Test: `tests/market/test_free_market_resolver.py`

**Steps:**

1. Write failing tests for case-contract precedence, role-based timeframe
   fallback, primary/fallback order, timeout/error isolation, and all-source
   failure.
2. Run the tests and verify the provider-neutral resolver is missing.
3. Implement request normalization and ordered provider fallback.
4. Run the tests and verify they pass.

### Task 3: Implement TqSdk Normalization

**Files:**
- Create: `src/trading_agent/market/providers/tqsdk.py`
- Test: `tests/market/test_tqsdk_provider.py`

**Steps:**

1. Write failing tests using a fake Tq API for real-contract discovery, daily
   and 60-minute bar conversion, OI conversion, settlement, trading calendar,
   metadata, and close-state handling.
2. Run the tests and verify the adapter is missing.
3. Implement lazy TqSdk imports, backend authentication, bounded waits, and
   normalization into `MarketDataSnapshot`.
4. Run the tests and verify they pass.

### Task 4: Implement AkShare Fallback

**Files:**
- Create: `src/trading_agent/market/providers/akshare.py`
- Test: `tests/market/test_akshare_provider.py`

**Steps:**

1. Write failing tests using a fake AkShare module for daily and 60-minute
   normalization, contract details, night-session dates, malformed upstream
   responses, and endpoint failure.
2. Run the tests and verify the adapter is missing.
3. Implement lazy AkShare imports and normalization.
4. Run the tests and verify they pass.

### Task 5: Add Exchange Daily Validation

**Files:**
- Create: `src/trading_agent/market/providers/validation.py`
- Test: `tests/market/test_exchange_validation.py`

**Steps:**

1. Write failing tests for official-data match, unavailable report, and
   conflicting price/OI/settlement.
2. Run the tests and verify the validator is missing.
3. Implement best-effort closed-daily validation.
4. Run the tests and verify they pass.

### Task 6: Configure the Local Runtime

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/trading_agent/config.py`
- Modify: `src/trading_agent/market/resolver.py`
- Modify: `src/trading_agent/api/app.py`
- Modify: `src/trading_agent/local_runtime.py`
- Modify: `.env.example`
- Modify: `.env.local.example`
- Modify: `docs/runbook.md`
- Test: `tests/test_bootstrap.py`
- Test: `tests/deployment/test_local_runtime.py`
- Test: `tests/market/test_market_resolver.py`

**Steps:**

1. Write failing tests for free-mode defaults, optional Tq credentials,
   dependency checks, configured resolver construction, and API wiring.
2. Run the tests and verify local mode still builds a null resolver.
3. Add pinned-compatible dependencies and configuration.
4. Wire `create_app()` and the worker to the same configured resolver.
5. Run the focused tests and verify they pass.

### Task 7: End-to-End Verification

**Files:**
- Modify: `tests/api/test_case_flow.py`
- Create: `tests/market/test_live_free_data.py`
- Modify: `docs/evaluation.md`

**Steps:**

1. Write an API integration test proving structured daily and 60-minute data
   remove screenshot blockers and appear in milestone audit details.
2. Run it and verify it fails before final wiring.
3. Complete the minimal wiring required by the test.
4. Run backend unit and integration tests.
5. Run lint and type checks.
6. Run Playwright end-to-end tests.
7. Run the opt-in live free-data smoke test for representative contracts when
   network access and a Tq account are available.
