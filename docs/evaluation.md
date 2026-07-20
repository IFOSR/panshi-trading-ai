# Evaluation and Release Gates

Vision evidence accuracy and deterministic strategy behavior are evaluated separately.
The release command is:

```bash
python -m evals.release_gate --fixture evals/fixtures/passing.json
```

Any unsupported exact number, critical safety violation, or strategy/action
contradiction blocks release. Benchmark splits are isolated by instrument,
contract period, timestamp, and terminal appearance. Strategy backtests consume
structured bars and include fees, slippage, price limits, rollover costs, and
unavailable fills.
