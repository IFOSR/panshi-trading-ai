from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from trading_agent.market.resolver import MarketDataSnapshot


@dataclass(frozen=True)
class MarketDataRequest:
    contract: str
    timeframe: str
    image_role: str
    evidence_cutoff_time: str | None = None


class MarketDataProvider(Protocol):
    name: str

    def fetch(self, request: MarketDataRequest) -> "MarketDataSnapshot | None":
        ...
