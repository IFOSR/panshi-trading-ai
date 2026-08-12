import json

import pytest

from trading_agent.clarification.models import ClarificationQuestion
from trading_agent.providers.base import (
    ClarificationRequest,
    ProviderResponseError,
)
from trading_agent.providers.clarification import DeepSeekClarificationProvider
from trading_agent.clarification.prompts import render_clarification_prompt
from trading_agent.providers.deepseek import _HttpRunner


def request() -> ClarificationRequest:
    return ClarificationRequest(
        clarification_id="clarification-1",
        case_id="case-1",
        source_analysis_id="analysis-1",
        user_message="日线已经收盘，持仓量减少 4425。",
        questions=[
            ClarificationQuestion(
                question_id="clarify-state-bar-closed",
                field="state_bar_closed",
                milestone_number=1,
                uncertainty="收盘状态未知。",
                question="日线是否收盘？",
                answer_examples=["已收盘", "未收盘"],
                blocking_issues=["BAR_CLOSE_UNKNOWN"],
            ),
            ClarificationQuestion(
                question_id="clarify-open-interest-change",
                field="open_interest_change",
                milestone_number=5,
                uncertainty="持仓量未知。",
                question="持仓量变化是多少？",
                answer_examples=["减少 4425"],
                blocking_issues=["OPEN_INTEREST_MISSING"],
            ),
        ],
        evidence_summary="CF2609 日线与 60 分钟截图。",
    )


def json_runner(payload: dict) -> _HttpRunner:
    def complete(
        messages: list[dict],
        *,
        model: str = "deepseek-chat",
        temperature: float = 0.0,
    ) -> str:
        return json.dumps(payload, ensure_ascii=False)

    runner = _HttpRunner()
    runner.complete = complete  # type: ignore[method-assign]
    return runner


def valid_payload() -> dict:
    return {
        "facts": [
            {
                "question_id": "clarify-state-bar-closed",
                "field": "state_bar_closed",
                "value": True,
                "explanation": "用户确认日线已收盘。",
            },
            {
                "question_id": "clarify-open-interest-change",
                "field": "open_interest_change",
                "value": -4425,
                "explanation": "用户提供持仓量减少 4425。",
            },
        ],
        "unresolved_question_ids": [],
        "interpretation": "用户补充了收盘状态和持仓量变化。",
    }


def test_deepseek_clarification_provider_uses_strict_text_schema(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def complete(
        messages: list[dict],
        *,
        model: str = "deepseek-chat",
        temperature: float = 0.0,
    ) -> str:
        captured["messages"] = messages
        captured["model"] = model
        return json.dumps(valid_payload(), ensure_ascii=False)

    runner = _HttpRunner()
    runner.complete = complete  # type: ignore[method-assign]

    provider = DeepSeekClarificationProvider(model="deepseek-chat", runner=runner)
    proposal = provider.interpret(request())

    assert proposal.provider == "deepseek"
    assert proposal.model == "deepseek-chat"
    assert len(proposal.facts) == 2
    assert proposal.facts[0].value is True
    assert proposal.facts[1].value == -4425
    assert proposal.facts[0].resolves_blockers == ["BAR_CLOSE_UNKNOWN"]
    assert "用户补充" in proposal.interpretation
    assert captured["model"] == "deepseek-chat"
    content = captured["messages"][0]["content"]
    assert render_clarification_prompt(request()) in str(content)


def test_deepseek_clarification_provider_rejects_invalid_response(
    monkeypatch,
) -> None:
    provider = DeepSeekClarificationProvider(
        runner=json_runner({"facts": "not-a-list"}),
    )

    with pytest.raises(ProviderResponseError):
        provider.interpret(request())


def test_deepseek_clarification_provider_rejects_fact_outside_open_questions(
    monkeypatch,
) -> None:
    payload = valid_payload()
    payload["facts"] = [
        {
            "question_id": "unrelated-question",
            "field": "unknown_field",
            "value": 1,
            "explanation": "不在开放问题范围内。",
        }
    ]

    provider = DeepSeekClarificationProvider(
        runner=json_runner(payload),
    )

    with pytest.raises(ProviderResponseError):
        provider.interpret(request())


def test_price_confirmation_question_accepts_direction_and_pattern_facts(
    monkeypatch,
) -> None:
    req = request()
    req.questions.append(
        ClarificationQuestion(
            question_id="clarify-price-confirmation",
            field="price_confirmation",
            milestone_number=7,
            uncertainty="确认状态未知。",
            question="执行周期是否出现突破？",
            answer_examples=["突破后回踩守住"],
            blocking_issues=["PRICE_NOT_CONFIRMED"],
            allowed_fact_fields=[
                "price_confirmation",
                "price_confirmation_direction",
                "price_confirmation_type",
            ],
        )
    )
    payload = valid_payload()
    payload["facts"] = [
        {
            "question_id": "clarify-price-confirmation",
            "field": "price_confirmation",
            "value": True,
            "explanation": "60 分钟突破后回踩守住。",
        },
        {
            "question_id": "clarify-price-confirmation",
            "field": "price_confirmation_direction",
            "value": "BULLISH",
            "explanation": "向上突破。",
        },
        {
            "question_id": "clarify-price-confirmation",
            "field": "price_confirmation_type",
            "value": "PULLBACK",
            "explanation": "回踩未跌回结构内。",
        },
    ]

    provider = DeepSeekClarificationProvider(
        runner=json_runner(payload),
    )
    proposal = provider.interpret(req)

    assert len(proposal.facts) == 3
    assert all(
        fact.question_id == "clarify-price-confirmation"
        for fact in proposal.facts
    )


def test_clarification_prompt_defines_strategy_enum_mappings() -> None:
    prompt = render_clarification_prompt(request())

    assert "BULLISH" in prompt
    assert "BEARISH" in prompt
    assert "BREAKOUT" in prompt
    assert "PULLBACK" in prompt
