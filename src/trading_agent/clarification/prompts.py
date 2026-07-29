import json

from trading_agent.providers.base import ClarificationRequest


def render_clarification_prompt(request: ClarificationRequest) -> str:
    questions = [
        {
            "question_id": question.question_id,
            "field": question.field,
            "allowed_fields": question.allowed_fact_fields,
            "question": question.question,
            "answer_examples": question.answer_examples,
        }
        for question in request.questions
    ]
    return "\n".join(
        [
            "你是中国期货策略系统的澄清信息解析器。",
            "只提取用户明确提供的信息，不得根据常识、截图摘要或策略需要猜测。",
            "只允许回答 open_questions 中列出的 question_id 和 field。",
            "无法明确解析的问题放入 unresolved_question_ids。",
            "输出值必须使用以下策略枚举，不得自行创造近义标签：",
            "- position_behavior_state:",
            "  - 多头增仓或空头减仓 -> LONG_BUILD_SHORT_COVER",
            "  - 空头增仓或多头减仓 -> SHORT_BUILD_LONG_EXIT",
            "  - 只明确总持仓增加、无法判断方向 -> POSITION_BUILDING",
            "  - 只明确总持仓减少、无法判断方向 -> POSITION_LIQUIDATION",
            "- state_bar_closed 和 execution_bar_closed: 只能输出 true 或 false。",
            "- open_interest_change: 只能输出数值，增加为正数，减少为负数。",
            "- price_confirmation: true 或 false，不能输出方向、形态或描述文本。",
            "- price_confirmation_direction: BULLISH 或 BEARISH。",
            "- price_confirmation_type:",
            "  - 突破 -> BREAKOUT",
            "  - 守住 -> HOLD",
            "  - 回踩或回抽确认 -> PULLBACK",
            "  - 结构失效 -> STRUCTURAL_FAILURE。",
            "用户同时说明价格确认、方向和形态时，必须使用同一 question_id "
            "拆成三个独立 fact：price_confirmation、"
            "price_confirmation_direction、price_confirmation_type。",
            "不要生成交易建议，不要修改风险限制，不要输出隐藏思维过程。",
            "",
            f"case_id: {request.case_id}",
            f"source_analysis_id: {request.source_analysis_id}",
            "open_questions:",
            json.dumps(questions, ensure_ascii=False, indent=2),
            "existing_evidence_summary:",
            request.evidence_summary,
            "user_message:",
            request.user_message,
        ]
    )
