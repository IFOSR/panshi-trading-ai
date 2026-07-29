from typing import Any, Protocol

from trading_agent.market.resolver import MarketDataSnapshot


class SnapshotValidator(Protocol):
    def validate(self, snapshot: MarketDataSnapshot) -> MarketDataSnapshot:
        ...


class AkShareExchangeDailyValidator:
    def __init__(self, *, module: Any | None = None) -> None:
        self.module = module

    def _module(self) -> Any:
        if self.module is None:
            import akshare  # type: ignore[import-not-found, import-untyped]

            self.module = akshare
        return self.module

    @staticmethod
    def _append(values: list[str], value: str) -> list[str]:
        return list(dict.fromkeys([*values, value]))

    def _unavailable(
        self,
        snapshot: MarketDataSnapshot,
        source: str,
    ) -> MarketDataSnapshot:
        return snapshot.model_copy(
            update={
                "quality_issues": self._append(
                    snapshot.quality_issues,
                    f"{source}_UNAVAILABLE",
                )
            }
        )

    def validate(self, snapshot: MarketDataSnapshot) -> MarketDataSnapshot:
        if snapshot.timeframe != "1d" or not snapshot.last_bar_closed:
            return snapshot
        exchange = snapshot.contract_metadata.get("exchange")
        if not exchange:
            return snapshot.model_copy(
                update={
                    "quality_issues": self._append(
                        snapshot.quality_issues,
                        "EXCHANGE_VALIDATION_SKIPPED",
                    )
                }
            )
        source = f"{exchange}_OFFICIAL_DAILY"
        latest = snapshot.bars[-1]
        trade_date = latest.trading_date.strftime("%Y%m%d")
        try:
            frame = self._module().get_futures_daily(
                start_date=trade_date,
                end_date=trade_date,
                market=str(exchange),
            )
        except Exception:
            return self._unavailable(snapshot, source)
        try:
            required = {
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "open_interest",
            }
            if frame is None or not required <= set(frame.columns):
                return self._unavailable(snapshot, source)
            rows = frame[
                frame["symbol"].astype(str).str.casefold()
                == snapshot.contract.casefold()
            ]
            if rows.empty:
                return self._unavailable(snapshot, source)
            row = rows.iloc[-1]
            conflicts = []
            for field in ("open", "high", "low", "close"):
                if abs(float(row[field]) - float(getattr(latest, field))) > 1e-9:
                    conflicts.append(field)
            if float(row["volume"]) != latest.volume:
                conflicts.append("volume")
            if float(row["open_interest"]) != latest.open_interest:
                conflicts.append("open_interest")
            official_settlement = row.get("settle")
            if (
                latest.settlement is not None
                and official_settlement not in (None, "")
                and float(official_settlement) > 0
                and abs(float(official_settlement) - latest.settlement) > 1e-9
            ):
                conflicts.append("settlement")
        except Exception:
            return self._unavailable(snapshot, source)
        if conflicts:
            return snapshot.model_copy(
                update={
                    "price_axis_verified": False,
                    "blocking_issues": self._append(
                        snapshot.blocking_issues,
                        "MARKET_DATA_VALIDATION_CONFLICT",
                    ),
                    "quality_issues": self._append(
                        snapshot.quality_issues,
                        "MARKET_DATA_VALIDATION_CONFLICT",
                    ),
                }
            )
        return snapshot.model_copy(
            update={
                "validation_sources": self._append(
                    snapshot.validation_sources,
                    source,
                )
            }
        )
