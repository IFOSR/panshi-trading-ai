from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta, timezone
import math
import re
import time as time_module
from typing import Any
from zoneinfo import ZoneInfo

from trading_agent.market.bars import MarketBar
from trading_agent.market.providers.base import MarketDataRequest
from trading_agent.market.resolver import MarketDataSnapshot


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _value(row: Any, name: str, default: Any = None) -> Any:
    if hasattr(row, "get"):
        return row.get(name, default)
    return getattr(row, name, default)


def _as_datetime(value: object) -> datetime:
    numeric = float(str(value))
    seconds = numeric / 1_000_000_000 if numeric > 10_000_000_000 else numeric
    return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(SHANGHAI)


def _as_optional_float(value: object) -> float | None:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _as_sessions(value: object) -> list[list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result: list[list[str]] = []
    for item in value:
        if (
            isinstance(item, Sequence)
            and not isinstance(item, (str, bytes))
            and len(item) >= 2
        ):
            result.append([str(item[0]), str(item[1])])
    return result


def _parse_clock(value: str) -> time:
    return time.fromisoformat(value)


def _session_end_for(
    start: datetime,
    sessions: Sequence[Sequence[str]],
) -> datetime | None:
    for raw_start, raw_end in sessions:
        segment_start = datetime.combine(
            start.date(),
            _parse_clock(raw_start),
            tzinfo=SHANGHAI,
        )
        segment_end = datetime.combine(
            start.date(),
            _parse_clock(raw_end),
            tzinfo=SHANGHAI,
        )
        if segment_end <= segment_start:
            segment_end += timedelta(days=1)
        candidate = start
        if candidate < segment_start and candidate.time() < time(6):
            candidate += timedelta(days=1)
        if segment_start <= candidate < segment_end:
            return segment_end
    return None


def _bar_close_time(
    *,
    start: datetime,
    trading_date: date,
    timeframe: str,
    sessions: Sequence[Sequence[str]],
) -> datetime:
    if timeframe == "1d":
        return datetime.combine(trading_date, time(15, 0), tzinfo=SHANGHAI)
    proposed = start + timedelta(hours=1)
    session_end = _session_end_for(start, sessions)
    return min(proposed, session_end) if session_end else proposed


def _trading_date_for(timestamp: datetime, open_dates: Sequence[date]) -> date:
    if timestamp.hour >= 20:
        return next(
            (candidate for candidate in open_dates if candidate > timestamp.date()),
            timestamp.date() + timedelta(days=1),
        )
    return timestamp.date()


class TqSdkMarketDataProvider:
    name = "tqsdk"

    def __init__(
        self,
        username: str,
        password: str,
        *,
        history_length: int = 240,
        timeout_seconds: float = 10.0,
        api_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.history_length = history_length
        self.timeout_seconds = timeout_seconds
        self.api_factory = api_factory or self._default_api_factory
        self.clock = clock or (lambda: datetime.now(SHANGHAI))

    def _default_api_factory(self) -> Any:
        from tqsdk import TqApi, TqAuth  # type: ignore[import-not-found, import-untyped]

        return TqApi(
            auth=TqAuth(self.username, self.password),
            web_gui=False,
        )

    @staticmethod
    def _product(contract: str) -> str:
        suffix = contract.rsplit(".", 1)[-1]
        match = re.match(r"([A-Za-z]+)", suffix)
        if not match:
            raise ValueError(f"cannot infer product from contract {contract}")
        return match.group(1).lower()

    @staticmethod
    def _provider_symbol(api: Any, contract: str, product: str) -> str:
        if "." in contract:
            exchange, instrument = contract.split(".", 1)
            return f"{exchange.upper()}.{instrument}"
        candidates = api.query_quotes(
            ins_class="FUTURE",
            product_id=product,
            expired=False,
        )
        normalized = contract.casefold()
        for candidate in candidates:
            if str(candidate).rsplit(".", 1)[-1].casefold() == normalized:
                return str(candidate)
        raise ValueError(f"contract {contract} was not found")

    def _wait_for_rows(self, api: Any, frame: Any) -> None:
        deadline = time_module.time() + self.timeout_seconds
        while len(frame) < 2 or not self._valid_rows(frame):
            if time_module.time() >= deadline:
                raise TimeoutError("TqSdk market data timed out")
            if api.wait_update(deadline=deadline) is False:
                raise TimeoutError("TqSdk market data timed out")

    @staticmethod
    def _valid_rows(frame: Any) -> list[Any]:
        rows: list[Any] = []
        for _, row in frame.iterrows():
            values = [
                _as_optional_float(_value(row, field))
                for field in ("open", "high", "low", "close")
            ]
            if all(value is not None and value > 0 for value in values):
                rows.append(row)
        return rows

    @staticmethod
    def _settlements(api: Any, symbol: str, history_length: int) -> dict[date, float]:
        try:
            frame = api.query_symbol_settlement(
                symbol,
                days=min(history_length, 400),
            )
        except Exception:
            return {}
        result: dict[date, float] = {}
        for _, row in frame.iterrows():
            raw_date = _value(row, "trading_day", _value(row, "date"))
            value = _as_optional_float(_value(row, "settlement"))
            if raw_date is None or value is None or value <= 0:
                continue
            result[getattr(raw_date, "date", lambda: raw_date)()] = value
        return result

    def fetch(self, request: MarketDataRequest) -> MarketDataSnapshot | None:
        duration = {"1d": 86_400, "60m": 3_600}.get(request.timeframe)
        if duration is None:
            raise ValueError(f"unsupported timeframe {request.timeframe}")
        api = self.api_factory()
        try:
            product = self._product(request.contract)
            symbol = self._provider_symbol(api, request.contract, product)
            info_frame = api.query_symbol_info(symbol)
            if len(info_frame) != 1:
                raise ValueError(f"expected one contract record for {symbol}")
            info = info_frame.iloc[0]
            frame = api.get_kline_serial(
                symbol,
                duration_seconds=duration,
                data_length=self.history_length,
            )
            self._wait_for_rows(api, frame)
            rows = self._valid_rows(frame)
            starts = [_as_datetime(_value(row, "datetime")) for row in rows]
            calendar = api.get_trading_calendar(
                min(starts).date() - timedelta(days=1),
                max(starts).date() + timedelta(days=7),
            )
            open_dates = sorted(
                getattr(_value(row, "date"), "date", lambda: _value(row, "date"))()
                for _, row in calendar.iterrows()
                if bool(_value(row, "trading"))
            )
            day_sessions = _as_sessions(_value(info, "trading_time_day"))
            night_sessions = _as_sessions(_value(info, "trading_time_night"))
            sessions = [*day_sessions, *night_sessions]
            settlements = (
                self._settlements(api, symbol, self.history_length)
                if request.timeframe == "1d"
                else {}
            )
            now = self.clock().astimezone(SHANGHAI)
            contract = symbol.rsplit(".", 1)[-1].lower()
            bars: list[MarketBar] = []
            for index, (row, start) in enumerate(zip(rows, starts, strict=True)):
                trading_date = _trading_date_for(start, open_dates)
                scheduled_close = _bar_close_time(
                    start=start,
                    trading_date=trading_date,
                    timeframe=request.timeframe,
                    sessions=sessions,
                )
                is_last = index == len(rows) - 1
                is_closed = not is_last or now >= scheduled_close
                cutoff = scheduled_close if is_closed else now
                open_interest = _as_optional_float(_value(row, "close_oi"))
                bars.append(
                    MarketBar(
                        contract=contract,
                        timeframe=request.timeframe,
                        timestamp=cutoff,
                        trading_date=trading_date,
                        open=float(_value(row, "open")),
                        high=float(_value(row, "high")),
                        low=float(_value(row, "low")),
                        close=float(_value(row, "close")),
                        volume=float(_value(row, "volume", 0)),
                        open_interest=open_interest or 0,
                        settlement=settlements.get(trading_date),
                        is_closed=is_closed,
                        source=self.name,
                    )
                )
            if len(bars) < 2:
                return None
            price_tick = _as_optional_float(_value(info, "price_tick"))
            upper_limit = _as_optional_float(_value(info, "upper_limit"))
            lower_limit = _as_optional_float(_value(info, "lower_limit"))
            latest_close = bars[-1].close
            near_limit = (
                (
                    bool(
                        (upper_limit and latest_close >= upper_limit - price_tick)
                        or (lower_limit and latest_close <= lower_limit + price_tick)
                    )
                )
                if price_tick and (upper_limit or lower_limit)
                else None
            )
            dominant_contract: str | None = None
            try:
                quote = api.get_quote(
                    f"KQ.m@{str(_value(info, 'exchange_id'))}.{product}"
                )
                dominant_contract = str(
                    _value(quote, "underlying_symbol", "")
                ).strip() or None
            except Exception:
                dominant_contract = None
            rollover_active = (
                dominant_contract.casefold() != symbol.casefold()
                if dominant_contract
                else None
            )
            expire_value = _value(info, "expire_datetime")
            expire_datetime = (
                _as_datetime(expire_value).isoformat()
                if _as_optional_float(expire_value)
                else None
            )
            metadata: dict[str, object] = {
                "exchange": str(_value(info, "exchange_id")),
                "provider_symbol": symbol,
                "product": str(_value(info, "product_id", product)),
                "price_tick": price_tick,
                "multiplier": _as_optional_float(_value(info, "volume_multiple")),
                "upper_limit": upper_limit,
                "lower_limit": lower_limit,
                "pre_settlement": _as_optional_float(_value(info, "pre_settlement")),
                "expire_datetime": expire_datetime,
                "trading_time_day": day_sessions,
                "trading_time_night": night_sessions,
                "dominant_contract": dominant_contract,
            }
            return MarketDataSnapshot(
                contract=contract,
                timeframe=request.timeframe,
                cutoff_time=bars[-1].timestamp,
                last_bar_closed=bars[-1].is_closed,
                price_axis_verified=True,
                rollover_active=rollover_active,
                near_price_limit=near_limit,
                sources=[self.name],
                contract_metadata=metadata,
                bars=bars,
            )
        finally:
            api.close()
