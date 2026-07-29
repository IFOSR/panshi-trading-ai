from trading_agent.clarification.models import (
    ClarificationFact,
    ClarificationQuestion,
)


def test_clarification_contract_accepts_dynamic_strategy_fields_and_steps() -> None:
    question = ClarificationQuestion(
        question_id="clarify-spread-regime",
        field="spread_regime",
        allowed_fact_fields=["spread_regime"],
        milestone_number=12,
        uncertainty="跨期价差状态未知。",
        question="请确认当前价差处于扩张还是收敛状态。",
        answer_examples=["价差扩张", "价差收敛"],
        blocking_issues=["SPREAD_REGIME_MISSING"],
    )
    fact = ClarificationFact(
        question_id=question.question_id,
        field="spread_regime",
        value="EXPANDING",
        explanation="用户明确说明价差正在扩张。",
        resolves_blockers=question.blocking_issues,
    )

    assert question.milestone_number == 12
    assert fact.field == "spread_regime"
