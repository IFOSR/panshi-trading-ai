from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext, evidence_refs_for


def _allowed_confirmation_types(strategy: str | None) -> set[str]:
    if strategy and "_BREAKOUT_" in strategy:
        return {"BREAKOUT", "HOLD"}
    if strategy and "_PULLBACK_" in strategy:
        return {"PULLBACK", "HOLD"}
    if strategy and strategy.startswith("RANGE_REVERSAL_"):
        return {"PULLBACK", "HOLD"}
    return set()


def evaluate(context: StrategyContext, strategy: str | None) -> MilestoneResult:
    required_direction = (
        "BULLISH" if strategy and strategy.endswith("_LONG")
        else "BEARISH" if strategy and strategy.endswith("_SHORT")
        else "UNKNOWN"
    )
    direction_matches = (
        required_direction != "UNKNOWN"
        and context.price_confirmation_direction == required_direction
    )
    allowed_types = _allowed_confirmation_types(strategy)
    type_matches = context.price_confirmation_type in allowed_types
    if context.price_confirmation is None:
        status = MilestoneStatus.BLOCKED
        result = "UNKNOWN"
        blockers = ["PRICE_NOT_CONFIRMED"]
        next_conditions = ["等待自动获取可验证的执行周期证据"]
        evidence_state = "UNKNOWN"
    elif context.price_confirmation is False:
        status = MilestoneStatus.CANDIDATE
        result = "NOT_TRIGGERED"
        blockers = []
        next_conditions = ["等待已收盘执行周期形成价格确认"]
        evidence_state = "KNOWN_FALSE"
    elif strategy is None:
        status = MilestoneStatus.CANDIDATE
        result = "NOT_TRIGGERED"
        blockers = []
        next_conditions = ["等待策略许可形成后再匹配执行周期确认"]
        evidence_state = "KNOWN_TRUE"
    elif not direction_matches:
        status = MilestoneStatus.CANDIDATE
        result = "NOT_TRIGGERED"
        blockers = ["CONFIRMATION_DIRECTION_MISMATCH"]
        next_conditions = ["等待与策略同方向的执行周期价格确认"]
        evidence_state = "KNOWN_TRUE"
    elif not type_matches:
        status = MilestoneStatus.CANDIDATE
        result = "NOT_TRIGGERED"
        blockers = ["CONFIRMATION_TYPE_MISMATCH"]
        next_conditions = ["等待符合策略形态的执行周期价格确认"]
        evidence_state = "KNOWN_TRUE"
    else:
        status = MilestoneStatus.CONFIRMED
        result = (
            f"{context.price_confirmation_direction}_"
            f"{context.price_confirmation_type}"
        )
        blockers = []
        next_conditions = []
        evidence_state = "KNOWN_TRUE"
    return MilestoneResult(
        number=7,
        code="PRICE_CONFIRMATION",
        status=status,
        result=result,
        rule_ids=["PC-001"],
        evidence_refs=evidence_refs_for(
            context,
            "price_confirmation",
            "price_confirmation_direction",
            "price_confirmation_type",
        ),
        blockers=blockers,
        next_conditions=next_conditions,
        details={
            "evidence_state": evidence_state,
            "required_direction": required_direction,
            "observed_direction": context.price_confirmation_direction,
            "confirmation_type": context.price_confirmation_type,
            "allowed_confirmation_types": sorted(allowed_types),
        },
    )
