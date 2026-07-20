# China Futures Trading Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an auditable China-futures Trading Agent that extracts evidence from screenshots, evaluates eight deterministic strategy milestones, applies independent risk rules, and renders a final action that cannot contradict the strategy state.

**Architecture:** Implement the typed domain and deterministic strategy kernel first, then add direct original-image multimodal extraction through Codex/GPT-5.6 with Kimi fallback, structured market-data verification, durable case workflows, APIs, and the two-layer strategy console. Store all case changes as immutable events, and treat the generated `ActionDecision` as the only source of truth for user-facing conclusions.

**Tech Stack:** Python, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Redis, NumPy, pytest, Codex CLI/GPT-5.6, Kimi Code fallback, Next.js, TypeScript, React, Playwright, Docker Compose, OpenTelemetry.

---

## Preconditions

- Run the work in a Git repository or dedicated worktree.
- Keep the approved design available at
  `docs/plans/2026-07-19-china-futures-trading-agent-design.md`.
- Do not connect an order gateway in the MVP.
- Do not use a screenshot-derived coordinate as an exact order price.
- Pin model versions and prompt versions before collecting benchmark results.
- Send the original image directly to Codex/GPT-5.6; do not add OpenCV, panel
  segmentation, local OCR, or chart reconstruction.

### Task 1: Bootstrap the Backend and Domain Package

**Files:**
- Create: `pyproject.toml`
- Create: `src/trading_agent/__init__.py`
- Create: `src/trading_agent/config.py`
- Create: `tests/test_bootstrap.py`
- Create: `.env.example`

**Step 1: Write the failing smoke test**

```python
# tests/test_bootstrap.py
from trading_agent.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.enable_order_execution is False
```

**Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_bootstrap.py -v
```

Expected: FAIL because the package and `Settings` do not exist.

**Step 3: Add the minimal project configuration**

```toml
# pyproject.toml
[project]
name = "china-futures-trading-agent"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.115",
  "pydantic-settings>=2.8",
  "sqlalchemy>=2.0",
  "asyncpg>=0.30",
  "redis>=5.2",
  "numpy>=2.2",
  "httpx>=0.28",
  "python-multipart>=0.0.20",
  "opentelemetry-api>=1.31",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.25",
  "ruff>=0.11",
  "mypy>=1.15",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

```python
# src/trading_agent/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_AGENT_")

    environment: str = "test"
    enable_order_execution: bool = False
```

**Step 4: Run verification**

Run:

```bash
uv sync
uv run pytest tests/test_bootstrap.py -v
uv run ruff check src tests
```

Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml src tests .env.example
git commit -m "chore: bootstrap trading agent backend"
```

### Task 2: Define the Evidence, Milestone, and Decision Contracts

**Files:**
- Create: `src/trading_agent/domain/enums.py`
- Create: `src/trading_agent/domain/evidence.py`
- Create: `src/trading_agent/domain/milestone.py`
- Create: `src/trading_agent/domain/decision.py`
- Create: `tests/domain/test_contracts.py`

**Step 1: Write failing contract tests**

```python
# tests/domain/test_contracts.py
import pytest
from pydantic import ValidationError

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import ActionType, MarketState


def test_decision_requires_blocking_steps_when_waiting_for_data() -> None:
    with pytest.raises(ValidationError):
        ActionDecision(
            action=ActionType.WAIT_FOR_DATA,
            market_state=MarketState.U,
            supporting_steps=[],
            blocking_steps=[],
            reason_codes=["CONTRACT_MISSING"],
            evidence_refs=[],
        )


def test_decision_can_represent_auditable_wait() -> None:
    decision = ActionDecision(
        action=ActionType.WAIT_FOR_DATA,
        market_state=MarketState.U,
        supporting_steps=[2, 4],
        blocking_steps=[1, 3, 7],
        reason_codes=["CONTRACT_MISSING"],
        evidence_refs=["evidence-001"],
    )

    assert decision.blocking_steps == [1, 3, 7]
```

**Step 2: Run the tests**

Run:

```bash
uv run pytest tests/domain/test_contracts.py -v
```

Expected: FAIL because the contracts do not exist.

**Step 3: Implement enums and validated contracts**

```python
# src/trading_agent/domain/enums.py
from enum import StrEnum


class MarketState(StrEnum):
    T_PLUS = "T+"
    T_MINUS = "T-"
    RANGE = "R"
    U = "U"


class MilestoneStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANDIDATE = "CANDIDATE"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"


class ActionType(StrEnum):
    WAIT_FOR_DATA = "WAIT_FOR_DATA"
    WAIT_FOR_SETUP = "WAIT_FOR_SETUP"
    WATCH_ENTRY = "WATCH_ENTRY"
    ENTER_CONDITIONAL = "ENTER_CONDITIONAL"
    HOLD = "HOLD"
    ADD_CONDITIONAL = "ADD_CONDITIONAL"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
```

```python
# src/trading_agent/domain/decision.py
from pydantic import BaseModel, Field, model_validator

from trading_agent.domain.enums import ActionType, MarketState


class ActionDecision(BaseModel):
    action: ActionType
    market_state: MarketState
    supporting_steps: list[int] = Field(default_factory=list)
    blocking_steps: list[int] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    strategy: str | None = None
    signal_stage: str | None = None
    next_milestone: str | None = None
    upgrade_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_blocked_actions(self) -> "ActionDecision":
        if self.action == ActionType.WAIT_FOR_DATA and not self.blocking_steps:
            raise ValueError("WAIT_FOR_DATA requires at least one blocking step")
        return self
```

Add `Evidence`, `EvidenceValue`, and `MilestoneResult` models with IDs,
provenance, confidence, status, rule IDs, inputs, blockers, and next conditions.

**Step 4: Run tests and static checks**

Run:

```bash
uv run pytest tests/domain/test_contracts.py -v
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/trading_agent/domain tests/domain
git commit -m "feat: add auditable strategy contracts"
```

### Task 3: Implement the Event-Sourced Trading Case

**Files:**
- Create: `src/trading_agent/domain/case.py`
- Create: `src/trading_agent/domain/events.py`
- Create: `src/trading_agent/services/case_projector.py`
- Create: `tests/domain/test_case_events.py`

**Step 1: Write failing event replay tests**

```python
# tests/domain/test_case_events.py
from trading_agent.domain.case import PositionDirection
from trading_agent.domain.events import CaseCreated, PositionUpdated
from trading_agent.services.case_projector import replay_case


def test_case_replay_restores_current_position() -> None:
    state = replay_case(
        [
            CaseCreated(case_id="case-1", instrument="rb", contract="rb2610"),
            PositionUpdated(
                case_id="case-1",
                direction=PositionDirection.LONG,
                quantity=2,
                average_cost=3295,
            ),
        ]
    )

    assert state.position.direction == PositionDirection.LONG
    assert state.position.quantity == 2
    assert state.position.average_cost == 3295
```

**Step 2: Run the test**

Run:

```bash
uv run pytest tests/domain/test_case_events.py -v
```

Expected: FAIL because events and projector are missing.

**Step 3: Implement immutable events and projector**

Use discriminated Pydantic event models for:

```text
CASE_CREATED
IMAGE_UPLOADED
IMAGE_PARSED
POSITION_UPDATED
MARKET_STATE_CHANGED
SIGNAL_ADVANCED
ADVICE_ISSUED
USER_ACTION_REPORTED
CASE_CLOSED
CASE_REVIEWED
```

Implement `replay_case(events)` as a pure function. Reject negative quantities,
contract changes without a new case, and position updates that omit direction.

**Step 4: Verify replay and serialization**

Run:

```bash
uv run pytest tests/domain/test_case_events.py -v
uv run pytest tests/domain -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/trading_agent/domain src/trading_agent/services tests/domain
git commit -m "feat: add event sourced trading cases"
```

### Task 4: Add Original-Image Intake and Direct Multimodal Quality Gates

**Files:**
- Create: `src/trading_agent/vision/image_quality.py`
- Create: `src/trading_agent/vision/privacy.py`
- Create: `tests/vision/test_image_quality.py`
- Add fixture: `tests/fixtures/charts/daily_boll_macd_volume.png`

**Step 1: Add the approved screenshot as a local test fixture**

Copy the representative screenshot into
`tests/fixtures/charts/daily_boll_macd_volume.png`. Strip metadata and ensure no
account identifiers are present.

**Step 2: Write failing original-image quality tests**

```python
# tests/vision/test_image_quality.py
from pathlib import Path

from trading_agent.vision.image_quality import inspect_image


def test_large_clear_chart_is_not_rejected() -> None:
    result = inspect_image(Path("tests/fixtures/charts/daily_boll_macd_volume.png"))

    assert result.is_readable is True
    assert "TOO_SMALL" not in result.issues
```

**Step 3: Run tests to confirm failure**

Run:

```bash
uv run pytest tests/vision -v
```

Expected: FAIL because the vision modules do not exist.

**Step 4: Implement non-transforming intake**

Implement:

- File existence, extension, byte-size, and SHA-256 checks.
- Duplicate detection using the original-image hash.
- Privacy-region hooks for account screenshots.
- Original-image artifact records.
- A model-reported quality result after direct multimodal inspection.

Do not transform, crop, segment, OCR, or reconstruct the image locally.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/vision -v
uv run ruff check src tests
```

Expected: PASS.

```bash
git add src/trading_agent/vision tests/vision tests/fixtures
git commit -m "feat: add original image intake"
```

### Task 5: Add Typed Codex and Kimi Multimodal Gateways

**Files:**
- Create: `src/trading_agent/providers/base.py`
- Create: `src/trading_agent/providers/codex.py`
- Create: `src/trading_agent/providers/kimi.py`
- Create: `src/trading_agent/vision/prompts.py`
- Create: `src/trading_agent/vision/evidence_merger.py`
- Create: `tests/providers/test_provider_contract.py`
- Create: `tests/vision/test_evidence_merger.py`

**Step 1: Write a failing provider contract test**

```python
# tests/providers/test_provider_contract.py
from trading_agent.providers.base import VisionRequest


def test_vision_request_requires_prompt_and_at_least_one_image() -> None:
    request = VisionRequest(
        prompt_version="chart-evidence-v1",
        images=["tests/fixtures/charts/daily_boll_macd_volume.png"],
        output_schema="ScreenshotEvidence",
    )

    assert request.prompt_version == "chart-evidence-v1"
```

**Step 2: Write a failing evidence-conflict test**

```python
# tests/vision/test_evidence_merger.py
from trading_agent.vision.evidence_merger import merge_evidence


def test_conflicting_model_and_market_contract_values_create_a_blocker() -> None:
    merged = merge_evidence(
        model={"contract": "rb2605"},
        market_data={"contract": "rb2610"},
    )

    assert "CONTRACT_CONFLICT" in merged.blocking_issues
    assert merged.allowed_usage == "BLOCKED"
```

**Step 3: Run tests**

Run:

```bash
uv run pytest tests/providers tests/vision/test_evidence_merger.py -v
```

Expected: FAIL.

**Step 4: Implement provider adapters and prompts**

The screenshot extraction prompt must require:

- Visible facts only.
- `null` for unknown fields.
- Visible evidence descriptions.
- Per-field confidence.
- No trading action.
- No exact number unless visible or tool-verified.
- Explicit contradictions and blockers.

Invoke Codex non-interactively with:

```text
codex exec --ephemeral --sandbox read-only \
  --model gpt-5.6-sol \
  --image <original-image> \
  --output-schema <screenshot-evidence-schema>
```

If Codex is unavailable, invoke Kimi Code against the same original-image path.
If Kimi reports that its current model cannot read images, return
`PROVIDER_UNAVAILABLE`; never synthesize evidence from text-only output.

Merge results using deterministic source precedence:

```text
Verified structured market data
  -> explicit visible text extracted by the multimodal model
  -> qualitative visual relation
```

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/providers tests/vision -v
```

Expected: PASS with network calls mocked.

```bash
git add src/trading_agent/providers src/trading_agent/vision tests
git commit -m "feat: add multimodal evidence extraction gateway"
```

### Task 6: Normalize China Futures Market Data and Indicators

**Files:**
- Create: `src/trading_agent/market/contracts.py`
- Create: `src/trading_agent/market/calendar.py`
- Create: `src/trading_agent/market/bars.py`
- Create: `src/trading_agent/quant/boll.py`
- Create: `src/trading_agent/quant/macd.py`
- Create: `src/trading_agent/quant/swings.py`
- Create: `tests/market/test_trading_date.py`
- Create: `tests/quant/test_indicators.py`
- Create: `tests/quant/test_causal_swings.py`

**Step 1: Write the night-session trading-date test**

```python
# tests/market/test_trading_date.py
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_agent.market.calendar import resolve_trading_date


def test_night_session_maps_to_next_trading_date() -> None:
    timestamp = datetime(2026, 7, 17, 21, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert resolve_trading_date(timestamp) == "2026-07-20"
```

Use an exchange calendar fixture rather than assuming every weekday is open.

**Step 2: Write known-value indicator tests**

Use a fixed bar fixture and assert exact BOLL and MACD values to a documented
tolerance. Add a test proving that a swing point is unavailable until its
right-side confirmation bars exist.

**Step 3: Run tests**

Run:

```bash
uv run pytest tests/market tests/quant -v
```

Expected: FAIL.

**Step 4: Implement market normalization**

Implement:

- Real, dominant, and continuous-contract identifiers.
- Calendar date and trading date.
- Exchange sessions and holiday provider interface.
- Bar-close state.
- OHLC, volume, total open interest, settlement, and data provenance.
- Versioned BOLL, MACD, ATR, and causal swing calculations.

Do not infer an exchange holiday solely from weekends.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/market tests/quant -v
uv run mypy src
```

Expected: PASS.

```bash
git add src/trading_agent/market src/trading_agent/quant tests/market tests/quant
git commit -m "feat: add futures market normalization and indicators"
```

### Task 7: Implement the Eight Strategy Milestones

**Files:**
- Create: `src/trading_agent/strategy/context.py`
- Create: `src/trading_agent/strategy/data_validity.py`
- Create: `src/trading_agent/strategy/market_state.py`
- Create: `src/trading_agent/strategy/strategy_permission.py`
- Create: `src/trading_agent/strategy/price_location.py`
- Create: `src/trading_agent/strategy/position_behavior.py`
- Create: `src/trading_agent/strategy/momentum.py`
- Create: `src/trading_agent/strategy/price_confirmation.py`
- Create: `src/trading_agent/strategy/evaluator.py`
- Create: `tests/strategy/test_milestone_pipeline.py`

**Step 1: Write a failing eight-step pipeline test**

```python
# tests/strategy/test_milestone_pipeline.py
from trading_agent.strategy.evaluator import evaluate_strategy
from tests.factories import make_bearish_transition_context


def test_bearish_transition_produces_eight_auditable_steps() -> None:
    result = evaluate_strategy(make_bearish_transition_context())

    assert [step.number for step in result.steps] == list(range(1, 9))
    assert result.steps[1].code == "MARKET_STATE"
    assert result.steps[1].result == "U_BEARISH_BIAS"
    assert result.steps[2].status == "BLOCKED"
```

**Step 2: Add anti-look-ahead and rule-ID tests**

Assert:

- Unclosed daily bars cannot switch the daily market state.
- Every milestone has at least one rule ID or blocker.
- MACD divergence alone does not confirm an entry.
- Total open-interest changes are not described as one-sided position changes.

**Step 3: Run tests**

Run:

```bash
uv run pytest tests/strategy -v
```

Expected: FAIL.

**Step 4: Implement pure milestone evaluators**

Each evaluator accepts a typed `StrategyContext` and returns a
`MilestoneResult`. Keep evaluators side-effect free.

Initial rule namespaces:

```text
DQ-*  data quality
MS-*  market state
SP-*  strategy permission
PL-*  price location
PB-*  position behavior
MO-*  momentum
PC-*  price confirmation
```

The pipeline must always produce all eight visible steps, including blocked
steps.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/strategy -v
uv run pytest tests/domain tests/market tests/quant tests/strategy -v
```

Expected: PASS.

```bash
git add src/trading_agent/strategy tests/strategy tests/factories.py
git commit -m "feat: add auditable strategy milestone engine"
```

### Task 8: Implement Independent Risk and Final Action Policy

**Files:**
- Create: `src/trading_agent/risk/models.py`
- Create: `src/trading_agent/risk/engine.py`
- Create: `src/trading_agent/decision/policy.py`
- Create: `tests/risk/test_risk_engine.py`
- Create: `tests/decision/test_action_policy.py`

**Step 1: Write high-risk contradiction tests**

```python
# tests/decision/test_action_policy.py
from trading_agent.decision.policy import decide_action
from trading_agent.domain.enums import ActionType
from tests.factories import (
    make_blocked_strategy_result,
    make_confirmed_entry_result,
)


def test_data_blocker_prevents_entry() -> None:
    decision = decide_action(make_blocked_strategy_result())

    assert decision.action == ActionType.WAIT_FOR_DATA


def test_risk_veto_overrides_confirmed_entry() -> None:
    decision = decide_action(
        make_confirmed_entry_result(risk_status="VETO")
    )

    assert decision.action != ActionType.ENTER_CONDITIONAL
```

**Step 2: Add position-specific tests**

Test:

- Empty position cannot receive `HOLD`, `REDUCE`, or `EXIT`.
- Unknown position cannot receive a single position-specific action.
- Adding requires a controlled-risk existing position and new confirmation.
- Forced exit has precedence over every other action.

**Step 3: Run tests**

Run:

```bash
uv run pytest tests/risk tests/decision -v
```

Expected: FAIL.

**Step 4: Implement risk and action policy**

Risk checks include:

- Data delay or missing bars.
- Unclosed state-period bar.
- Contract or period mismatch.
- Dominant-contract rollover.
- Price-limit proximity.
- Excessive stop distance.
- Missing account risk for sizing.
- Correlated portfolio exposure.
- Unknown market or order state.

Implement decision precedence exactly as documented in the approved design.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/risk tests/decision -v
uv run pytest -v
```

Expected: PASS.

```bash
git add src/trading_agent/risk src/trading_agent/decision tests
git commit -m "feat: enforce risk veto and final action policy"
```

### Task 9: Add a Constrained Response Renderer

**Files:**
- Create: `src/trading_agent/rendering/models.py`
- Create: `src/trading_agent/rendering/prompt.py`
- Create: `src/trading_agent/rendering/validator.py`
- Create: `src/trading_agent/rendering/service.py`
- Create: `tests/rendering/test_response_validator.py`

**Step 1: Write contradiction tests**

```python
# tests/rendering/test_response_validator.py
from trading_agent.domain.enums import ActionType
from trading_agent.rendering.validator import validate_rendered_response
from tests.factories import make_decision


def test_renderer_rejects_entry_text_for_wait_decision() -> None:
    decision = make_decision(action=ActionType.WAIT_FOR_SETUP)
    rendered = {
        "action": "ENTER_CONDITIONAL",
        "summary": "Open a long position now.",
    }

    result = validate_rendered_response(decision, rendered)

    assert result.is_valid is False
    assert "ACTION_MISMATCH" in result.errors
```

**Step 2: Add completeness tests**

Require:

- Current action.
- Direct reason.
- Supporting and blocking steps.
- Upgrade conditions.
- Invalidation conditions.
- Next milestone.
- Data limitations.

**Step 3: Run tests**

Run:

```bash
uv run pytest tests/rendering -v
```

Expected: FAIL.

**Step 4: Implement renderer and validator**

Pass the immutable `ActionDecision`, milestone results, and evidence summaries
to the language model. Parse the response into a typed presentation model and
reject:

- Action changes.
- New numeric levels without evidence references.
- Unsupported strategy names.
- Missing blockers.
- Conditions not present in the decision object.

On validation failure, return a deterministic template rather than retrying
unboundedly.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/rendering -v
uv run pytest tests/decision tests/rendering -v
```

Expected: PASS.

```bash
git add src/trading_agent/rendering tests/rendering
git commit -m "feat: add constrained decision response renderer"
```

### Task 10: Persist Events and Expose Case APIs

**Files:**
- Create: `src/trading_agent/db/base.py`
- Create: `src/trading_agent/db/models.py`
- Create: `src/trading_agent/db/repositories.py`
- Create: `src/trading_agent/api/app.py`
- Create: `src/trading_agent/api/cases.py`
- Create: `src/trading_agent/api/images.py`
- Create: `src/trading_agent/api/analysis.py`
- Create: `tests/api/test_case_flow.py`
- Create: `alembic.ini`
- Create: `alembic/versions/0001_case_events.py`

**Step 1: Write an end-to-end API test**

```python
# tests/api/test_case_flow.py
from fastapi.testclient import TestClient

from trading_agent.api.app import app


def test_create_case_upload_image_and_request_analysis() -> None:
    client = TestClient(app)

    created = client.post(
        "/v1/cases",
        json={"instrument": "rb", "contract": "rb2610"},
    )
    case_id = created.json()["case_id"]

    analysis = client.post(f"/v1/cases/{case_id}/analysis")

    assert analysis.status_code == 200
    assert len(analysis.json()["milestones"]) == 8
```

**Step 2: Run the API test**

Run:

```bash
uv run pytest tests/api/test_case_flow.py -v
```

Expected: FAIL.

**Step 3: Implement persistence and APIs**

Endpoints:

```text
POST   /v1/cases
GET    /v1/cases/{case_id}
POST   /v1/cases/{case_id}/images
POST   /v1/cases/{case_id}/position
POST   /v1/cases/{case_id}/analysis
GET    /v1/cases/{case_id}/analyses
GET    /v1/cases/{case_id}/analyses/{analysis_id}
POST   /v1/cases/{case_id}/actions
POST   /v1/cases/{case_id}/close
```

Persist immutable events and materialized case state in one transaction. Add
idempotency keys to upload, position update, and analysis commands.

**Step 4: Run migration and API tests**

Run:

```bash
uv run alembic upgrade head
uv run pytest tests/api -v
```

Expected: PASS against the test database.

**Step 5: Commit**

```bash
git add src/trading_agent/db src/trading_agent/api tests/api alembic.ini alembic
git commit -m "feat: add persistent case and analysis APIs"
```

### Task 11: Add the Durable Analysis Workflow

**Files:**
- Create: `src/trading_agent/workflows/analysis.py`
- Create: `src/trading_agent/workflows/activities.py`
- Create: `src/trading_agent/workflows/worker.py`
- Create: `tests/workflows/test_analysis_workflow.py`

**Step 1: Write a workflow replay test**

Create a Temporal test-environment test that verifies:

- Repeated analysis commands are idempotent.
- A provider timeout retries the extraction activity.
- A risk decision is not retried as an LLM call.
- The same inputs produce the same strategy and action objects.

**Step 2: Run the workflow test**

Run:

```bash
uv run pytest tests/workflows/test_analysis_workflow.py -v
```

Expected: FAIL.

**Step 3: Implement the workflow**

Workflow sequence:

```text
Load case
  -> inspect and segment images
  -> extract direct multimodal evidence from the original image
  -> resolve market data
  -> merge and quality-gate evidence
  -> calculate indicators
  -> evaluate eight milestones
  -> run risk engine
  -> decide action
  -> render and validate response
  -> persist analysis event
```

Keep nondeterministic provider calls inside Temporal activities.

**Step 4: Verify**

Run:

```bash
uv run pytest tests/workflows -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/trading_agent/workflows tests/workflows
git commit -m "feat: add durable analysis workflow"
```

### Task 12: Build the Two-Layer Strategy Console

**Files:**
- Create: `web/package.json`
- Create: `web/app/page.tsx`
- Create: `web/app/cases/[caseId]/page.tsx`
- Create: `web/components/decision-summary.tsx`
- Create: `web/components/strategy-milestone-rail.tsx`
- Create: `web/components/milestone-card.tsx`
- Create: `web/components/evidence-viewer.tsx`
- Create: `web/components/change-report.tsx`
- Create: `web/lib/api.ts`
- Create: `web/tests/strategy-console.spec.ts`

**Step 1: Scaffold Next.js and add a failing Playwright test**

```typescript
// web/tests/strategy-console.spec.ts
import { expect, test } from "@playwright/test";

test("shows final action and all eight strategy milestones", async ({ page }) => {
  await page.goto("/cases/case-1");

  await expect(page.getByTestId("current-action")).toContainText("等待");
  await expect(page.getByTestId("strategy-milestone")).toHaveCount(8);
});
```

**Step 2: Run the test**

Run:

```bash
cd web
pnpm test:e2e
```

Expected: FAIL because the console does not exist.

**Step 3: Implement the first layer**

The top summary displays:

- Current action.
- Market state.
- Enabled strategy.
- Current milestone.
- Key blockers.
- Next milestone.
- Data cutoff and close state.

The milestone rail displays all eight steps even when blocked.

**Step 4: Implement the second layer**

Expanded milestone cards display:

- Inputs.
- Key values.
- Rule IDs.
- Evidence crops.
- Structured-data comparisons.
- Confidence and provenance.
- Previous-current changes.
- Next conditions.

Use explicit visual states for confirmed, candidate, blocked, and invalidated.
Do not use color as the only status signal.

**Step 5: Verify and commit**

Run:

```bash
cd web
pnpm lint
pnpm test:e2e
```

Expected: PASS on desktop and mobile viewports.

```bash
git add web
git commit -m "feat: add auditable strategy console"
```

### Task 13: Build the Offline Evaluation Harness

**Files:**
- Create: `evals/datasets/schema.json`
- Create: `evals/run_vision_eval.py`
- Create: `evals/run_strategy_eval.py`
- Create: `evals/metrics.py`
- Create: `evals/release_gate.py`
- Create: `tests/evals/test_release_gate.py`
- Create: `docs/evaluation.md`

**Step 1: Write a failing release-gate test**

```python
# tests/evals/test_release_gate.py
from evals.release_gate import evaluate_release


def test_release_fails_on_any_critical_safety_violation() -> None:
    result = evaluate_release(
        {
            "critical_metadata_precision": 0.999,
            "critical_safety_violations": 1,
            "unsupported_exact_numbers": 0,
        }
    )

    assert result.passed is False
```

**Step 2: Run the test**

Run:

```bash
uv run pytest tests/evals/test_release_gate.py -v
```

Expected: FAIL.

**Step 3: Implement benchmark metrics**

Include:

- Critical-field accepted precision and coverage.
- Visible numeric exact match.
- Screenshot-role Macro-F1.
- New-versus-old change Macro-F1.
- Market-state Macro-F1.
- Signal-transition accuracy.
- Calibration error and risk-coverage curve.
- Unsupported exact-number rate.
- Strategy/action contradiction rate.
- P50 and P95 latency.
- Cost per accepted analysis.

Add hard gates before computing a weighted model score.

**Step 4: Add strategy backtest interfaces**

The strategy evaluator must consume structured historical bars, not screenshots.
It records fees, slippage, price limits, rollovers, unavailable fills, and
look-ahead checks.

**Step 5: Verify and commit**

Run:

```bash
uv run pytest tests/evals -v
uv run python evals/release_gate.py --fixture evals/fixtures/passing.json
```

Expected: PASS for the passing fixture and nonzero exit for a failing fixture.

```bash
git add evals tests/evals docs/evaluation.md
git commit -m "feat: add model and strategy evaluation gates"
```

### Task 14: Add Deployment, Security, and Observability

**Files:**
- Create: `docker-compose.yml`
- Create: `infra/otel-collector.yaml`
- Create: `src/trading_agent/observability.py`
- Create: `src/trading_agent/security/retention.py`
- Create: `src/trading_agent/security/audit.py`
- Create: `tests/security/test_retention.py`
- Create: `docs/runbook.md`

**Step 1: Write retention and audit tests**

Test:

- Raw images expire according to configured policy.
- Evidence and decision metadata remain replayable after raw-image deletion.
- Account identifiers are never written to model traces.
- Every analysis logs model, prompt, strategy, risk, and rule versions.

**Step 2: Run tests**

Run:

```bash
uv run pytest tests/security -v
```

Expected: FAIL.

**Step 3: Implement local infrastructure**

Docker Compose services:

```text
postgres
redis
minio
temporal
temporal-ui
otel-collector
api
worker
web
```

Configure health checks and named volumes. Keep all order-execution settings
disabled and absent from public APIs.

**Step 4: Run the complete verification suite**

Run:

```bash
docker compose up -d postgres redis minio temporal
uv run alembic upgrade head
uv run pytest -v
uv run ruff check src tests evals
uv run mypy src
cd web && pnpm lint && pnpm test:e2e
```

Expected: all commands PASS.

**Step 5: Commit**

```bash
git add docker-compose.yml infra src/trading_agent/observability.py \
  src/trading_agent/security tests/security docs/runbook.md
git commit -m "chore: add secure observable local deployment"
```

## Final Release Checklist

- All eight milestone outputs are visible and auditable.
- The final action is generated by the deterministic action policy.
- Renderer contradiction tests pass.
- Critical missing data produces a blocker.
- Exact prices have structured or explicit-text provenance.
- Risk veto overrides every strategy action.
- New screenshot analyses include a change report.
- Event replay reproduces the same strategy and action objects.
- Model and prompt versions pass the offline release gate.
- Shadow mode is completed before real-user action recommendations.
- Automatic order execution remains disabled.

## Execution Handoff

Plan complete and saved to
`docs/plans/2026-07-19-china-futures-trading-agent-implementation.md`.

Two execution options:

1. Subagent-Driven (this session): dispatch a fresh subagent per task and review
   between tasks.
2. Parallel Session (separate): open a new session with
   `superpowers:executing-plans` and execute tasks with checkpoints.
