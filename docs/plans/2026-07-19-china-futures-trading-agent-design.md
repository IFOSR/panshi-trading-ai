# China Futures Trading Agent Design

Date: 2026-07-19
Status: Approved

## 1. Product Definition

The product is a multimodal, continuous-conversation trading decision and
position-management assistant for China's futures market.

Users provide:

- Natural-language questions.
- One or more market screenshots.
- Contract, position, cost, stop, executed actions, and risk constraints when
  required.

The system maintains a persistent trading case and answers:

- What is the current market state?
- Which strategy, if any, is permitted?
- Which strategy milestone has been reached?
- What is confirmed, pending, blocked, or invalid?
- What should an empty-position, long-position, or short-position user do now?
- What event would upgrade or invalidate the conclusion?

The first release does not place orders.

## 2. Core Design Principle

The system must not ask a multimodal model to infer a trade directly from an
arbitrary screenshot.

The responsibility boundary is:

```text
Multimodal model
  -> extracts visible evidence

Structured market data and quantitative services
  -> calculate exact values

Deterministic strategy state machine
  -> evaluates strategy milestones

Independent risk engine
  -> allows, reduces, or vetoes an action

Language model
  -> explains the immutable decision object
```

The final answer must be a deterministic projection of strategy outputs. The
language model cannot change the action, strategy, signal phase, triggers, or
invalidation conditions.

## 3. User Experience

The interface uses a two-layer strategy console.

### 3.1 First Layer: Decision Summary

The summary always displays:

```text
Current action
Market state
Enabled strategy
Current strategy milestone
Key blockers
Next milestone
Data cutoff time
```

Example:

```text
Current action: Wait for confirmation
Market state: U, bearish transition
Enabled strategy: None
Progress: Step 5 of 8
Blockers: Contract unknown; daily bar close unconfirmed
Next milestone: 60-minute price confirmation
```

### 3.2 First Layer: Strategy Milestones

The user sees all eight core strategy steps:

| Step | Output |
| --- | --- |
| 1. Data validity | Contract, period, timestamp, bar-close and source quality |
| 2. Market state | T+, T-, R, or U |
| 3. Strategy permission | Breakout, pullback, range reversal, or no strategy |
| 4. Price location | BOLL, swing points, range boundary, support and resistance |
| 5. Volume and position behavior | Position building, liquidation, exhaustion, or ineffective movement |
| 6. Momentum | MACD strengthening, weakening, divergence, or recovery |
| 7. Price confirmation | Breakout, hold, pullback confirmation, or structural failure |
| 8. Risk and action | Wait, enter, hold, add, reduce, exit, or request information |

Each milestone has one of four statuses:

```text
CONFIRMED
CANDIDATE
BLOCKED
INVALIDATED
```

### 3.3 Second Layer: Audit Details

Each milestone can be expanded to show:

- Inputs used by the step.
- Extracted and verified indicator values.
- Screenshot regions supporting the result.
- Structured-data values used for verification.
- Strategy rule identifiers.
- Current value versus rule threshold.
- Confidence and provenance.
- Changes from the previous analysis.
- Why the step passed, is pending, is blocked, or became invalid.
- Requirements for the next milestone.

This is an auditable strategy execution record, not a display of hidden
chain-of-thought.

## 4. Input Design

### 4.1 User Input

The natural-language parser extracts:

- User question and primary decision intent.
- Instrument and real contract.
- Position direction, quantity, average cost, and stop.
- Executed entry, add, reduce, or exit actions.
- Expected holding period.
- Account or trade risk limit.
- User explanations of custom screenshot indicators.

### 4.2 Screenshot Roles

Supported screenshot roles:

```text
STATE_DAILY
EXECUTION_60M
MEMBER_POSITION
CONTRACT_ROLLOVER
ACCOUNT_POSITION
AUXILIARY
```

Each screenshot record stores:

- Image role.
- Instrument and real contract.
- Continuous-contract and adjustment information.
- Timeframe.
- Data cutoff and trading date.
- Whether the latest bar is closed.
- Source application or terminal.
- Indicator names and parameters.
- Direct multimodal extraction output and per-field confidence.
- Screenshot regions and visual evidence.
- Relationship to the previous screenshot.
- Quality issues and allowed usage.

## 5. Screenshot Processing

The image pipeline performs:

```text
Upload
  -> privacy masking
  -> original-image validation
  -> Codex/GPT-5.6 direct multimodal extraction
  -> Kimi direct multimodal fallback when Codex is unavailable
  -> contract and time resolution
  -> structured market-data verification
  -> evidence merge
  -> quality gate
```

For a typical daily chart containing BOLL, position behavior, MACD, and volume,
the system sends the unmodified original image to the multimodal model with a
strict JSON schema. It does not use OpenCV, panel segmentation, local OCR, or
chart reconstruction.

The system must not hard-code candle colors. Color conventions are defined by a
terminal profile or reported as uncertain by the multimodal model.

### 5.1 Allowed Screenshot Usage

```text
EXACT
QUALITATIVE_ONLY
BLOCKED
```

- `EXACT` requires verified structured values or explicit values visibly read
  by the multimodal model.
- `QUALITATIVE_ONLY` allows structural observations but not exact order prices.
- `BLOCKED` prevents strategy progression until critical information is fixed.

Exact trigger prices, stops, and position sizing cannot be generated solely by
estimating chart coordinates.

### 5.2 Evidence Contract

```json
{
  "image_role": "STATE_DAILY",
  "instrument": {
    "value": null,
    "confidence": 0,
    "sources": []
  },
  "timeframe": {
    "value": "1d",
    "confidence": 0.99,
    "sources": ["period_selector"]
  },
  "cutoff_time": null,
  "last_bar_closed": null,
  "observations": [
    {
      "type": "PRICE_BELOW_BOLL_MID",
      "value": true,
      "confidence": 0.94,
      "region_id": "price_panel",
      "provenance": "vision"
    }
  ],
  "blocking_issues": [
    "Instrument is missing",
    "Latest bar close is unconfirmed"
  ],
  "allowed_usage": "QUALITATIVE_ONLY"
}
```

## 6. China Futures Data Requirements

The normalized market-data model must support:

- Real contracts, dominant contracts, and continuous contracts.
- Continuous-contract adjustment method.
- Calendar date and trading date, including night sessions.
- OHLC, volume, and total open interest at each bar close.
- Settlement price.
- Exchange, contract multiplier, and minimum price tick.
- Listing and expiration dates.
- Trading sessions and holidays.
- Margin, fees, and same-day close rules.
- Price limits and temporary exchange adjustments.
- Contract rollover and liquidity changes.
- Member position data when available.
- Account, order, and fill state for future extensions.

Indicator implementations must be versioned because terminal formulas, EMA
initialization, and adjusted price series can differ.

## 7. Strategy State Machine

### 7.1 Market States

```text
T+  bullish trend
T-  bearish trend
R   range
U   uncertain, transitional, or disordered
```

### 7.2 Strategy Types

```text
TREND_BREAKOUT_LONG
TREND_PULLBACK_LONG
TREND_BREAKOUT_SHORT
TREND_PULLBACK_SHORT
RANGE_REVERSAL_LONG
RANGE_REVERSAL_SHORT
```

### 7.3 Strategy Evaluation Sequence

```text
Data validity
  -> market state
  -> strategy permission
  -> price location
  -> volume and position behavior
  -> momentum
  -> price confirmation
  -> risk decision
  -> position-specific action
```

Strategy steps return typed results and rule identifiers. They do not return
natural-language trade recommendations.

## 8. Final Action Policy

The final action is calculated as:

```text
Action = Policy(
  data_validity,
  market_state,
  strategy_permission,
  signal_phase,
  price_confirmation,
  risk_permission,
  position_state
)
```

### 8.1 Action Types

```text
WAIT_FOR_DATA
WAIT_FOR_SETUP
WATCH_ENTRY
ENTER_CONDITIONAL
HOLD
ADD_CONDITIONAL
REDUCE
EXIT
```

### 8.2 Decision Precedence

```text
Forced exit
  -> risk veto
  -> data blocker
  -> position invalidation
  -> reduce
  -> add
  -> new entry
  -> wait
```

### 8.3 Hard Rules

- Entry requires valid data, an enabled strategy, price confirmation, and risk
  approval.
- Adding requires an existing controlled-risk position and a new independent
  confirmation.
- Missing contract, timeframe, bar-close, or price precision blocks exact
  actions.
- A divergence, BOLL touch, or position change cannot independently trigger an
  entry.
- A risk veto overrides every strategy signal.
- Position-specific advice requires a confirmed position direction.

### 8.4 Decision Object

```json
{
  "action": "WAIT_FOR_SETUP",
  "action_label": "Wait for confirmation",
  "position_scope": "EMPTY_POSITION",
  "strategy": null,
  "market_state": "U_BEARISH_BIAS",
  "signal_stage": "NO_VALID_SETUP",
  "supporting_steps": [2, 4, 5, 6],
  "blocking_steps": [1, 3, 7, 8],
  "reason_codes": [
    "MARKET_TRANSITIONAL",
    "NO_ENABLED_STRATEGY",
    "PRICE_NOT_CONFIRMED"
  ],
  "next_milestone": "Confirm the contract and use a 60-minute chart to verify price structure",
  "upgrade_conditions": [],
  "invalidation_conditions": [],
  "missing_information": [
    "Real contract",
    "Latest daily bar close state",
    "Position state",
    "60-minute execution chart"
  ],
  "evidence_refs": [
    "evidence-price-panel-001",
    "evidence-macd-panel-001"
  ]
}
```

The response-generation model receives this object as immutable input. A schema
validator rejects any response whose action or conditions contradict it.

## 9. User-Facing Final Conclusion

The conclusion card always contains:

```text
What to do now
Why
Which strategy steps support it
Which strategy steps block it
Position-specific handling
Upgrade conditions
Invalidation conditions
Next user or market milestone
Data and precision limitations
```

When the position is unknown, the response displays separate branches for an
empty position, existing long position, and existing short position. It does
not invent a single position-specific action.

Every new analysis displays:

```text
Previous result
  -> new evidence
  -> changed strategy steps
  -> updated action
  -> next milestone
```

## 10. System Architecture

```text
Web or App
  -> API Gateway
  -> Upload and Privacy Service
  -> Durable Case Workflow
      -> Intent Parser
      -> Screenshot Parser
      -> Market Data Resolver
      -> Quantitative Indicator Service
      -> Strategy State Machine
      -> Risk Engine
      -> Action Policy
      -> Response Renderer
  -> Case Event Store and Audit Log
```

Recommended implementation:

- Next.js for the client.
- FastAPI and Pydantic for typed APIs.
- Temporal for durable case workflows.
- PostgreSQL and TimescaleDB for case state, events, and market bars.
- Object storage for original images.
- Redis for cache, idempotency, and short-lived session state.
- NumPy and versioned pure-Python functions for quantitative calculations.
- OpenTelemetry, Prometheus, and Grafana for observability.

The durable source of truth is the case event store, not an LLM conversation
window.

## 11. Direct Multimodal Model Routing

The initial production route is:

```text
Original screenshot
  -> Codex CLI with GPT-5.6 and --image
  -> strict ScreenshotEvidence JSON schema

Codex unavailable
  -> Kimi Code direct-image attempt
  -> if image capability is unavailable, return PROVIDER_UNAVAILABLE

Critical conflict or missing field
  -> human/user confirmation
```

Codex/GPT-5.6 is the primary production provider. Kimi is a failure fallback,
not an ensemble vote. Models must use structured output. Model versions,
prompts, original-image hashes, schemas, and provider results are versioned and
must pass an evaluation gate before promotion.

## 12. Evaluation

Visual model evaluation and trading-strategy evaluation are separate.

### 12.1 Evaluation Dataset

The initial benchmark should contain:

- 12,000 single screenshots.
- 3,000 previous-current screenshot pairs.
- 1,000 degraded or adversarial screenshots.
- Standard charts generated from known structured data.
- Real screenshots across terminals, themes, sizes, and crop patterns.
- Daily, 60-minute, member-position, rollover, and account views.

Training and test splits are isolated by instrument, contract period, time, and
terminal appearance.

### 12.2 Release Gates

| Area | Metric | Gate |
| --- | --- | --- |
| Critical metadata | Accepted precision | >= 99.5% |
| Critical metadata | Automatic coverage | >= 85% |
| Critical visible numbers | Exact field match | >= 98% |
| Screenshot role | Macro-F1 | >= 97% |
| Screenshot change detection | Macro-F1 | >= 90% |
| Market state | Macro-F1 | >= 85% |
| Signal transition | Accuracy | >= 90% |
| Calibration | Expected calibration error | <= 0.05 |
| Unsupported exact numbers | Count | 0 |
| Critical safety violations | Count | 0 |
| Trigger and invalidation coverage | Coverage | 100% |
| End-to-end latency | P95 | <= 8 seconds |

Evaluation uses accepted precision rather than forcing the model to answer every
image. Abstention is a required capability.

### 12.3 Strategy Evaluation

Strategy evaluation uses structured historical data and must:

- Prevent look-ahead in swing-point and divergence detection.
- Use walk-forward and held-out tests.
- Model fees, slippage, same-day close costs, price limits, rollover, and
  unfilled orders.
- Compare the incremental value of open interest, MACD, member positions, and
  multiple timeframes.
- Report performance by instrument, direction, market state, and year.
- Progress through historical backtest, shadow mode, simulation, and controlled
  validation.

Screenshot parsing is evaluated on evidence accuracy. Strategy quality is
evaluated on rule correctness, risk behavior, and cost-adjusted results.

## 13. MVP Scope

The first release includes:

- Natural-language and multi-image input.
- Screenshot role confirmation.
- Persistent cases and event history.
- Position updates.
- Daily market state and 60-minute execution.
- All eight strategy milestone outputs.
- Deterministic final action policy.
- Current-versus-previous analysis.
- Evidence, confidence, blockers, triggers, and invalidations.
- Risk veto and audit logging.

The first release excludes:

- Automatic order placement.
- Full-market real-time scanning.
- Screenshot-only exact order prices.
- Unsupported paid personalized advisory behavior.
- Uncontrolled parameter optimization.

## 14. Acceptance Criteria

The product is acceptable when:

- Users can see every core strategy milestone.
- Every milestone links to verifiable evidence and rules.
- The final action is consistent with every milestone.
- No response introduces evidence absent from the decision object.
- Critical missing information results in a visible blocker.
- New screenshots produce an explicit change report.
- Empty, long, and short positions receive different action handling.
- Every actionable result has upgrade and invalidation conditions.
- Every model and strategy version can be replayed from the audit log.
