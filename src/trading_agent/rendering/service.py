from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import PositionDirection
from trading_agent.rendering.models import PositionBranch, RenderedDecision


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


def _position_guidance(
    scope: PositionDirection,
    decision: ActionDecision,
) -> str:
    if decision.action.value == "HOLD":
        return "维持当前仓位，暂不加仓；监控结构失效条件与下一策略里程碑。"
    if decision.action.value == "EXIT":
        return "按策略退出当前持仓，不等待新的入场确认。"
    if decision.action.value == "REDUCE":
        return "降低当前仓位风险，完成后按更新后的风险边界重新评估。"
    if decision.action.value == "ADD_CONDITIONAL":
        return "仅在新的同向价格确认和风险许可同时成立后加仓。"
    if decision.action.value == "ENTER_CONDITIONAL":
        return "策略条件与风险许可均已满足；按计划建立新仓，不追价。"
    if scope == PositionDirection.FLAT:
        return "不建立新仓，等待所有阻断步骤解除。"
    if scope == PositionDirection.LONG:
        return "保持多仓操作冻结，等待当前阻断步骤解除后重新评估。"
    return "保持空仓操作冻结，等待当前阻断步骤解除后重新评估。"


def position_branches_for_decision(
    decision: ActionDecision,
    branch_decisions: dict[PositionDirection, ActionDecision] | None = None,
) -> list[PositionBranch]:
    scopes = (
        [PositionDirection.FLAT, PositionDirection.LONG, PositionDirection.SHORT]
        if decision.position_scope == PositionDirection.UNKNOWN
        else [decision.position_scope]
    )
    labels = {
        PositionDirection.FLAT: "空仓分支",
        PositionDirection.LONG: "多仓分支",
        PositionDirection.SHORT: "空头持仓分支",
    }
    return [
        PositionBranch(
            scope=scope,
            action=(
                branch_decisions[scope].action
                if branch_decisions and scope in branch_decisions
                else decision.action
            ),
            label=labels[scope],
            guidance=_position_guidance(
                scope,
                branch_decisions[scope]
                if branch_decisions and scope in branch_decisions
                else decision,
            ),
        )
        for scope in scopes
    ]


def render_decision(
    decision: ActionDecision,
    branch_decisions: dict[PositionDirection, ActionDecision] | None = None,
) -> RenderedDecision:
    return RenderedDecision(
        action=decision.action,
        summary=ACTION_LABELS[decision.action.value],
        supporting_steps=decision.supporting_steps,
        blocking_steps=decision.blocking_steps,
        upgrade_conditions=decision.upgrade_conditions,
        invalidation_conditions=decision.invalidation_conditions,
        next_milestone=decision.next_milestone,
        data_limitations=decision.missing_information,
        position_branches=position_branches_for_decision(decision, branch_decisions),
    )
