import json

import pytest

from trading_agent.conversation.models import ConversationRequest
from trading_agent.providers.base import ProviderResponseError
from trading_agent.providers.conversation import DeepSeekConversationProvider
from trading_agent.providers.deepseek import _HttpRunner, render_conversation_prompt


def request() -> ConversationRequest:
    return ConversationRequest(
        case_id="case-1",
        source_analysis_id="analysis-1",
        user_message="为什么结论是等待？",
        strategy_manifest={
            "strategy_id": "structure_confirmation",
            "display_name": "结构确认策略",
            "version": "1.0.0",
        },
        decision={
            "action": "WAIT",
            "market_state": "U",
            "blocking_steps": [7],
            "reason_codes": ["PRICE_NOT_CONFIRMED"],
        },
        milestones=[{"number": 7, "status": "BLOCKED", "result": "NOT_TRIGGERED"}],
        rendered={"summary": "等待 60 分钟价格确认。"},
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
        "answer": "因为第 7 步价格确认尚未触发。",
        "suggested_questions": ["什么条件下会触发？"],
    }


def test_deepseek_conversation_provider_uses_immutable_analysis_schema(
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

    provider = DeepSeekConversationProvider(model="deepseek-chat", runner=runner)
    reply = provider.reply(request())

    assert reply.source_analysis_id == "analysis-1"
    assert reply.answer == "因为第 7 步价格确认尚未触发。"
    assert reply.provider == "deepseek"
    assert reply.model == "deepseek-chat"
    assert captured["model"] == "deepseek-chat"
    content = captured["messages"][0]["content"]
    assert render_conversation_prompt(request()) in str(content)


def test_deepseek_conversation_provider_rejects_invalid_response(
    monkeypatch,
) -> None:
    provider = DeepSeekConversationProvider(
        runner=json_runner({"answer": ""}),
    )

    with pytest.raises(ProviderResponseError):
        provider.reply(request())
