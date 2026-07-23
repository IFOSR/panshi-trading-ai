# Free China Futures Market Data Design

Date: 2026-07-23
Status: Approved

## Goal

Fill screenshot evidence gaps with free China-futures market data while
preserving the existing deterministic eight-step strategy and local,
Docker-free runtime.

## Scope

The first implementation supports:

- Real futures contracts from SHFE, INE, DCE, CZCE, CFFEX, and GFEX.
- Daily and 60-minute OHLCV.
- Open interest and open-interest change.
- Settlement and previous settlement where available.
- Contract multiplier, price tick, price limits, expiry, and trading sessions.
- Trading calendar and night-session trading-date attribution.
- Dominant-contract mapping and rollover detection.
- Daily member-position ranking as supporting evidence.
- Best-effort exchange daily-data validation.

Account position, average cost, stop price, and account risk remain user or
broker-account inputs. The implementation does not place orders.

## Architecture

```text
Case + screenshot evidence
        |
        v
FreeMarketDataResolver
        |
        +-- TqSdkProvider (primary when a free Tq account is configured)
        |
        +-- AkShareProvider (automatic fallback)
        |
        +-- ExchangeDailyValidator (best-effort official-data check)
        |
        v
MarketDataSnapshot
        |
        v
Existing indicator calculations and evidence merge
        |
        v
Eight deterministic strategy milestones
```

OpenBB is not used. Tushare is not required.

## Provider Rules

### TqSdk

TqSdk is the primary source when both backend credentials are configured.
It supplies real-time quotes, daily and 60-minute bars, open interest,
contract metadata, trading calendar, settlement data, dominant mapping, and
member ranking.

The credentials are backend service credentials. Product users do not log in.

### AkShare

AkShare is enabled without credentials and is the default local fallback. It
supplies Sina futures bars and quotes plus exchange daily reports, contract
details, member ranking, and warehouse data where the upstream page is
available.

AkShare failures must not crash an analysis. They produce a source failure and
allow the existing conversational clarification path to request missing data.

### Exchange Validation

Closed daily bars are compared with exchange daily reports when available.

- An exact match records the exchange source as a validation source.
- An unavailable report records a non-blocking quality warning.
- A price, volume, open-interest, or settlement conflict blocks exact strategy
  use with `MARKET_DATA_VALIDATION_CONFLICT`.

## Contract and Time Rules

The case contract is authoritative when present. Screenshot contracts are used
only when the case has no contract. A conflict remains blocking.

Image roles supply a safe timeframe fallback:

- `STATE_DAILY` -> `1d`
- `EXECUTION_60M` -> `60m`

Night-session timestamps are assigned to the next open trading date. The
latest bar is marked closed only when the provider timestamps and exchange
session boundaries prove it is closed. Uncertain close state remains blocking.

## Strategy Mapping

| Step | Structured data |
| --- | --- |
| 1. Data validity | Contract, timeframe, cutoff, close state, source, validation |
| 2. Market state | Closed daily OHLCV and versioned indicators |
| 3. Strategy permission | Deterministic output from steps 1, 2, and 4 |
| 4. Price location | Daily prices, BOLL, swings, ATR |
| 5. Position behavior | Volume, total open interest, OI change, ranking support |
| 6. Momentum | Daily MACD and price structure |
| 7. Price confirmation | Closed real-contract 60-minute bars |
| 8. Risk and action | Latest price, limits, multiplier, user risk inputs |

CCYD remains a derived or terminal-specific indicator. Price and open-interest
inputs are supplied, but the indicator is not treated as verified until its
formula is confirmed.

## Failure Behavior

- TqSdk unavailable -> try AkShare.
- AkShare endpoint unavailable -> preserve screenshot evidence and blockers.
- All sources unavailable -> `MARKET_DATA_UNAVAILABLE`.
- Insufficient history -> `MARKET_HISTORY_INSUFFICIENT`.
- Official validation conflict -> `MARKET_DATA_VALIDATION_CONFLICT`.
- Current bar unclosed -> existing unclosed-bar blockers remain active.

No data-source failure may silently generate an entry, add, or exact price.

## Testing

Tests use provider fakes and fixed Shanghai timestamps. Network calls are not
part of the default unit suite.

Required coverage:

- Contract and timeframe resolution.
- TqSdk normalization.
- AkShare normalization and endpoint failure.
- Primary/fallback order.
- Night-session trading-date attribution.
- Closed versus unclosed bars.
- Official validation match, unavailability, and conflict.
- Evidence provenance and step-1 audit details.
- Local runtime dependency and configuration.
- Inline API analysis with the configured resolver.

An opt-in live smoke test covers representative contracts from all five
domestic futures exchanges plus INE.
