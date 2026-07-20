from trading_agent.domain.decision import ActionDecision
from trading_agent.rendering.models import RenderedDecision


ACTION_LABELS = {
    "WAIT_FOR_DATA": "等待补齐数据",
    "WAIT_FOR_SETUP": "等待策略条件",
    "WATCH_ENTRY": "观察入场条件",
    "ENTER_CONDITIONAL": "条件满足后入场",
    "HOLD": "继续持有并监控失效条件",
    "ADD_CONDITIONAL": "新确认后条件加仓",
    "REDUCE": "降低仓位风险",
    "EXIT": "退出持仓",
}


def render_decision(decision: ActionDecision) -> RenderedDecision:
    return RenderedDecision(
        action=decision.action,
        summary=ACTION_LABELS[decision.action.value],
        supporting_steps=decision.supporting_steps,
        blocking_steps=decision.blocking_steps,
        upgrade_conditions=decision.upgrade_conditions,
        invalidation_conditions=decision.invalidation_conditions,
        next_milestone=decision.next_milestone,
        data_limitations=decision.missing_information,
    )
