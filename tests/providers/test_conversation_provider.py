import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from trading_agent.conversation.models import ConversationRequest
from trading_agent.providers.base import ProviderResponseError
from trading_agent.providers.conversation import CodexConversationProvider


def request() -> ConversationRequest:
    return ConversationRequest(
        case_id="case-1",
        source_analysis_id="analysis-1",
        user_message="为什么不是继续持有？",
        strategy_manifest={
            "strategy_id": "structure_confirmation",
            "display_name": "结构确认策略",
            "version": "1.0.0",
        },
        decision={"action": "EXIT", "supporting_steps": [2, 3, 8]},
        milestones=[
            {
                "number": 2,
                "code": "MARKET_STATE",
                "status": "CONFIRMED",
                "result": "T-",
            }
        ],
        rendered={"summary": "退出持仓"},
    )


def test_codex_conversation_provider_uses_immutable_analysis_schema(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def runner(command, timeout, cwd, stdin, env):
        captured.update(command=command, stdin=stdin)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "answer": "第 2 步确认空头趋势，最终动作是退出。",
                    "suggested_questions": ["什么条件下可以重新入场？"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexConversationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    reply = provider.reply(request())

    command = captured["command"]
    assert isinstance(command, list)
    assert "--image" not in command
    assert "--output-schema" in command
    assert reply.source_analysis_id == "analysis-1"
    assert reply.provider == "codex"
    assert "不得修改动作、策略、里程碑或风险结论" in str(captured["stdin"])
    assert '"action":"EXIT"' in str(captured["stdin"])


def test_codex_conversation_provider_rejects_invalid_response(monkeypatch) -> None:
    def runner(command, timeout, cwd, stdin, env):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps({"answer": "", "unexpected": "field"}),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexConversationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    with pytest.raises(ProviderResponseError):
        provider.reply(request())
