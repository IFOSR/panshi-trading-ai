# Evaluation and Release Gates

Vision evidence accuracy and deterministic strategy behavior are benchmarked
separately, then combined by the production release gate.

Run a standalone vision benchmark with:

```bash
python -m evals.run_vision_eval path/to/vision.jsonl \
  --provider codex \
  --model gpt-5.6-sol \
  --prompt-version chart-evidence-v2 \
  --dataset-version vision-benchmark-v1
```

Run the production release gate with both datasets:

```bash
python -m evals.release_gate \
  --vision-dataset path/to/vision.jsonl \
  --vision-provider codex \
  --vision-model gpt-5.6-sol \
  --vision-prompt-version chart-evidence-v2 \
  --vision-dataset-version vision-benchmark-v1 \
  --strategy-dataset path/to/strategy.json
```

Vision benchmark input contains only immutable labels and original-image paths.
It must not contain `prediction`, latency, or cost fields. The evaluator reads
each original image and executes the explicitly selected provider, model, and
prompt version. It rejects a result if the provider reports different version
metadata, so a precomputed or substituted prediction cannot enter release
metrics.

Single-image records are scored as `NEW`. Change-detection records provide
`previous_image_path`; the evaluator executes both unmodified originals and
compares their structured evidence fingerprints. The visual provider is not
asked to emit an action, signal transition, trigger, or invalidation.

All vision release records must use the `test` split, share the requested
`dataset_version`, and have unique original-image content hashes as well as
unique `record_id` values. They must reference existing image files. Renaming
or copying the same image cannot increase the independent sample count.
Production release requires at least 1,000 test records; this threshold cannot
be lowered from the release CLI. The initial full benchmark target remains
12,000 single screenshots, 3,000 previous-current pairs, and 1,000 degraded or
adversarial screenshots.

The strategy evaluator owns signal-stage accuracy, upgrade/invalidation
coverage, action consistency, 100% production execution coverage, 100%
strategy-selection accuracy, and coverage of all six approved strategy types.
The combined gate also rejects any unsupported exact number or critical safety
violation. A vision dataset without a strategy dataset is never sufficient for
production release.

Benchmark splits are isolated by instrument, contract period, timestamp, and
terminal appearance. Strategy datasets conform to
`evals/datasets/strategy_schema.json`. Each case contains the historical
decision context and a fill time, but no supplied orders. The evaluator runs
the production `AnalysisWorkflow`, maps its immutable action to a target
position, and generates backtest fills from that decision.

Structured bars include both an exchange timestamp and a China-futures
`trading_date`. Fees, slippage, price limits, rollover costs, unavailable fills,
and same-trading-date close fees are applied to the generated fills. Night and
day sessions with different calendar dates still incur the same-day close fee
when they share a `trading_date`.

Fixture threshold smoke checks remain available:

```bash
python -m evals.release_gate --fixture evals/fixtures/passing.json
python -m evals.release_gate --fixture evals/fixtures/failing.json
```

Fixture mode only verifies threshold arithmetic. It always returns a failed
production release status because it does not execute original images through
the selected multimodal provider.

## Free Market Data Gate

The default test suite uses deterministic provider fakes and does not call
external market-data services. Before a local release, run:

```bash
TRADING_AGENT_MARKET_DATA_PROVIDER=free \
RUN_LIVE_MARKET_DATA=1 \
.local/venv/bin/python -m pytest tests/market/test_live_free_data.py -v
```

Acceptance requires at least 21 daily and 60-minute bars for the real contract,
positive prices, non-negative open interest, and explicit source provenance.
When TqSdk credentials are configured, TqSdk is the primary source; otherwise
AkShare is the expected fallback.
