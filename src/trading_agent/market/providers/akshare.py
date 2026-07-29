from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
import math
from queue import Queue
import re
from threading import Thread
from typing import Any
from zoneinfo import ZoneInfo

from trading_agent.market.bars import MarketBar
from trading_agent.market.providers.base import MarketDataRequest
from trading_agent.market.resolver import MarketDataSnapshot


SHANGHAI = ZoneInfo("Asia/Shanghai")
EXCHANGE_CODES = {
    "上海期货交易所": "SHFE",
    "上海国际能源交易中心": "INE",
    "大连商品交易所": "DCE",
    "郑州商品交易所": "CZCE",
    "中国金融期货交易所": "CFFEX",
    "广州期货交易所": "GFEX",
}


def _number(value: object) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    result = float(match.group())
    return result if math.isfinite(result) else None


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif hasattr(value, "to_pydatetime"):
        result = value.to_pydatetime()
    else:
        result = datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        result = result.replace(tzinfo=SHANGHAI)
    return result.astimezone(SHANGHAI)


def _date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return _datetime(value).date()


def _trading_date(timestamp: datetime, open_dates: Sequence[date]) -> date:
    if timestamp.hour >= 20:
        return next(
            (candidate for candidate in open_dates if candidate > timestamp.date()),
            timestamp.date() + timedelta(days=1),
        )
    return timestamp.date()


class AkShareMarketDataProvider:
    name = "akshare"

    def __init__(
        self,
        *,
        module: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.module = module
        self.clock = clock or (lambda: datetime.now(SHANGHAI))
        self.timeout_seconds = timeout_seconds

    def _call(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        result: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                result.put((True, function(*args, **kwargs)))
            except BaseException as exc:
                result.put((False, exc))

        thread = Thread(target=invoke, daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            raise TimeoutError("AkShare market data timed out")
        succeeded, value = result.get_nowait()
        if succeeded:
            return value
        if isinstance(value, BaseException):
            raise value
        raise RuntimeError("AkShare call failed without an exception")

    def _module(self) -> Any:
        if self.module is None:
            import akshare  # type: ignore[import-not-found, import-untyped]

            self.module = akshare
        return self.module

    @staticmethod
    def _required_columns(frame: Any, fields: set[str]) -> None:
        missing = sorted(fields - set(frame.columns))
        if missing:
            raise ValueError(
                "AkShare response missing required columns: " + ", ".join(missing)
            )

    def _contract_metadata(self, module: Any, symbol: str) -> dict[str, object]:
        try:
            frame = self._call(module.futures_contract_detail, symbol=symbol)
        except Exception:
            return {}
        if not {"item", "value"} <= set(frame.columns):
            return {}
        details = {
            str(row["item"]).strip(): str(row["value"]).strip()
            for _, row in frame.iterrows()
        }
        exchange_name = details.get("上市交易所")
        return {
            "exchange": EXCHANGE_CODES.get(exchange_name or "", exchange_name),
            "provider_symbol": symbol,
            "product_name": details.get("交易品种"),
            "price_tick": _number(details.get("最小变动价位")),
            "multiplier": _number(details.get("交易单位")),
            "limit_rule": details.get("涨跌停板幅度"),
            "margin_rule": details.get("最低交易保证金"),
            "trading_time": details.get("交易时间"),
            "last_trading_day_rule": details.get("最后交易日"),
        }

    def _open_dates(self, module: Any) -> list[date]:
        try:
            frame = self._call(module.tool_trade_date_hist_sina)
        except Exception:
            return []
        if "trade_date" not in frame.columns:
            return []
        return sorted(_date(value) for value in frame["trade_date"].tolist())

    def _daily_bars(
        self,
        frame: Any,
        *,
        contract: str,
        now: datetime,
    ) -> list[MarketBar]:
        self._required_columns(
            frame,
            {"date", "open", "high", "low", "close", "volume", "hold"},
        )
        rows = list(frame.iterrows())
        bars: list[MarketBar] = []
        for index, (_, row) in enumerate(rows):
            trading_date = _date(row["date"])
            scheduled_close = datetime.combine(
                trading_date,
                time(15, 0),
                tzinfo=SHANGHAI,
            )
            is_last = index == len(rows) - 1
            is_closed = not is_last or now >= scheduled_close
            cutoff = scheduled_close if is_closed else now
            settlement = _number(row.get("settle"))
            bars.append(
                MarketBar(
                    contract=contract,
                    timeframe="1d",
                    timestamp=cutoff,
                    trading_date=trading_date,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    open_interest=float(row["hold"]),
                    settlement=settlement if settlement and settlement > 0 else None,
                    is_closed=is_closed,
                    source=self.name,
                )
            )
        return bars

    def _minute_bars(
        self,
        frame: Any,
        *,
        contract: str,
        now: datetime,
        open_dates: Sequence[date],
    ) -> list[MarketBar]:
        self._required_columns(
            frame,
            {"datetime", "open", "high", "low", "close", "volume", "hold"},
        )
        rows = list(frame.iterrows())
        bars: list[MarketBar] = []
        for index, (_, row) in enumerate(rows):
            scheduled_close = _datetime(row["datetime"])
            is_last = index == len(rows) - 1
            is_closed = not is_last or now >= scheduled_close
            cutoff = scheduled_close if is_closed else now
            bars.append(
                MarketBar(
                    contract=contract,
                    timeframe="60m",
                    timestamp=cutoff,
                    trading_date=_trading_date(scheduled_close, open_dates),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    open_interest=float(row["hold"]),
                    is_closed=is_closed,
                    source=self.name,
                )
            )
        return bars

    def _risk_flags(
        self,
        module: Any,
        *,
        symbol: str,
        metadata: dict[str, object],
    ) -> tuple[bool | None, bool | None, str | None]:
        product_name = metadata.get("product_name")
        if not product_name:
            return None, None, None
        try:
            frame = self._call(
                module.futures_zh_realtime,
                symbol=str(product_name),
            )
        except Exception:
            return None, None, None
        required = {"symbol", "trade", "presettlement", "volume", "position"}
        if frame is None or not required <= set(frame.columns):
            return None, None, None
        normalized_symbol = symbol.upper()
        product = re.match(r"[A-Z]+", normalized_symbol)
        if product is None:
            return None, None, None
        dominant_symbol = f"{product.group()}0"
        contract_rows = frame[
            frame["symbol"].astype(str).str.upper() == normalized_symbol
        ]
        dominant_rows = frame[
            frame["symbol"].astype(str).str.upper() == dominant_symbol
        ]
        if contract_rows.empty or dominant_rows.empty:
            return None, None, None
        contract_row = contract_rows.iloc[-1]
        dominant_row = dominant_rows.iloc[-1]
        signature_fields = (
            "trade",
            "settlement",
            "presettlement",
            "volume",
            "position",
        )
        rollover_active = not all(
            _number(contract_row.get(field)) == _number(dominant_row.get(field))
            for field in signature_fields
        )
        limit_rule = str(metadata.get("limit_rule") or "")
        limit_match = re.search(r"(\d+(?:\.\d+)?)\s*%", limit_rule)
        price_tick = _number(metadata.get("price_tick"))
        latest_price = _number(contract_row.get("trade"))
        previous_settlement = _number(contract_row.get("presettlement"))
        near_price_limit: bool | None = None
        if (
            limit_match
            and price_tick
            and latest_price
            and previous_settlement
        ):
            ratio = float(limit_match.group(1)) / 100
            upper_limit = previous_settlement * (1 + ratio)
            lower_limit = previous_settlement * (1 - ratio)
            near_price_limit = (
                latest_price >= upper_limit - price_tick
                or latest_price <= lower_limit + price_tick
            )
        dominant_contract = (
            normalized_symbol if rollover_active is False else dominant_symbol
        )
        return rollover_active, near_price_limit, dominant_contract

    def fetch(self, request: MarketDataRequest) -> MarketDataSnapshot | None:
        module = self._module()
        symbol = request.contract.rsplit(".", 1)[-1].upper()
        contract = symbol.lower()
        now = self.clock().astimezone(SHANGHAI)
        if request.timeframe == "1d":
            frame = self._call(module.futures_zh_daily_sina, symbol=symbol)
            bars = self._daily_bars(frame, contract=contract, now=now)
        elif request.timeframe == "60m":
            frame = self._call(
                module.futures_zh_minute_sina,
                symbol=symbol,
                period="60",
            )
            bars = self._minute_bars(
                frame,
                contract=contract,
                now=now,
                open_dates=self._open_dates(module),
            )
        else:
            raise ValueError(f"unsupported timeframe {request.timeframe}")
        if len(bars) < 2:
            return None
        metadata = self._contract_metadata(module, symbol)
        rollover_active, near_price_limit, dominant_contract = self._risk_flags(
            module,
            symbol=symbol,
            metadata=metadata,
        )
        if dominant_contract:
            metadata["dominant_contract"] = dominant_contract
        return MarketDataSnapshot(
            contract=contract,
            timeframe=request.timeframe,
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=bars[-1].is_closed,
            price_axis_verified=True,
            rollover_active=rollover_active,
            near_price_limit=near_price_limit,
            sources=[self.name],
            contract_metadata=metadata,
            bars=bars,
        )
