from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestCosts:
    fees: float
    slippage: float
    rollover_cost: float
    unavailable_fills: int


def net_pnl(gross_pnl: float, costs: BacktestCosts) -> float:
    return gross_pnl - costs.fees - costs.slippage - costs.rollover_cost
