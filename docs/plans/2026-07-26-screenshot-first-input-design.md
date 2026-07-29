# Screenshot-First Input Design

## Goal

Reduce the normal user journey to one required market input: the original daily
or main-structure screenshot. Public market facts must come from multimodal
extraction plus the configured free market-data resolver.

## User Inputs

- Required: one original daily or main-structure image.
- Required safety gate: local privacy/model-processing confirmation.
- Optional: one natural-language sentence containing account-private context,
  such as position direction, quantity, cost, or stop.
- Optional advanced overrides: contract, structured position, risk limits, and
  an execution-period screenshot.

The default question is: "请基于截图和公开行情，严格按八步策略判断当前如何操作。"
Risk defaults remain 1% account risk, 0.5% proposed risk, and 3% maximum stop
distance.

## Screenshot Contract

The UI tells users to keep these regions visible:

1. Contract or instrument title.
2. Timeframe label.
3. Main candlestick area.
4. Complete price axis.
5. Latest bar and visible date/time.
6. Indicator names when indicators are shown.

Volume, open interest, bar-close status, and 60-minute confirmation are not
required screenshot fields because structured public data supplies them.

## Data Flow

1. Create the case from the optional message and optional contract override.
2. Preserve the position parsed by the backend unless the user explicitly
   supplies a structured position override.
3. Always persist conservative risk defaults unless the user changes advanced
   values.
4. Upload the original daily screenshot to Codex.
5. Extract the contract and chart facts from the screenshot.
6. Resolve daily and synthetic 60-minute public market data.
7. Run the deterministic eight-step strategy and return only genuinely
   account-private clarification questions.

## Acceptance

- A request containing only the daily image and privacy confirmation succeeds.
- A message such as "我有多单30手" is preserved instead of being overwritten by
  a default flat position.
- Missing risk form fields receive conservative defaults.
- The home page shows a concrete screenshot checklist and labels all public
  market data as automatic.
- A new real CF2609 case completes with zero public-data clarification questions.
