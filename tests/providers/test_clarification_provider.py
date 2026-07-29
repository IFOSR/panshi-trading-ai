import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from trading_agent.clarification.models import ClarificationQuestion
from trading_agent.providers.base import (
    ClarificationRequest,
    ProviderResponseError,
)
from trading_agent.providers.clarification import CodexClarificationProvider
from trading_agent.clarification.prompts import render_clarification_prompt


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


def test_codex_clarification_provider_uses_strict_text_schema(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def runner(command, timeout, cwd, stdin, env):
        captured.update(
            command=command,
            timeout=timeout,
            cwd=cwd,
            stdin=stdin,
            env=env,
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "facts": [
                        {
                            "question_id": "clarify-state-bar-closed",
                            "field": "state_bar_closed",
                            "value": True,
                            "explanation": "用户明确说明日线已收盘。",
                        },
                        {
                            "question_id": "clarify-open-interest-change",
                            "field": "open_interest_change",
                            "value": -4425,
                            "explanation": "用户说明持仓量减少 4425。",
                        },
                    ],
                    "unresolved_question_ids": [],
                    "interpretation": "日线已收盘，持仓量变化为 -4425。",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexClarificationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    proposal = provider.interpret(request())

    command = captured["command"]
    assert isinstance(command, list)
    assert "--image" not in command
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert "--output-schema" in command
    assert proposal.clarification_id == "clarification-1"
    assert proposal.provider == "codex"
    assert proposal.facts[0].resolves_blockers == ["BAR_CLOSE_UNKNOWN"]
    assert "只提取用户明确提供" in str(captured["stdin"])


def test_codex_clarification_provider_rejects_invalid_response(monkeypatch) -> None:
    def runner(command, timeout, cwd, stdin, env):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("{}", encoding="utf-8")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexClarificationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    with pytest.raises(ProviderResponseError):
        provider.interpret(request())


def test_codex_clarification_provider_rejects_fact_outside_open_questions(
    monkeypatch,
) -> None:
    def runner(command, timeout, cwd, stdin, env):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "facts": [
                        {
                            "question_id": "invented-question",
                            "field": "contract",
                            "value": "CF2609",
                            "explanation": "越界字段。",
                        }
                    ],
                    "unresolved_question_ids": [],
                    "interpretation": "错误输出。",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexClarificationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    with pytest.raises(ProviderResponseError):
        provider.interpret(request())


def test_price_confirmation_question_accepts_direction_and_pattern_facts(
    monkeypatch,
) -> None:
    price_request = request().model_copy(
        update={
            "questions": [
                ClarificationQuestion(
                    question_id="clarify-price-confirmation",
                    field="price_confirmation",
                    milestone_number=7,
                    uncertainty="执行周期价格确认未知。",
                    question="是否形成价格确认，并说明方向和形态？",
                    answer_examples=["向下突破后回踩未站回"],
                    blocking_issues=["PRICE_NOT_CONFIRMED"],
                )
            ],
            "user_message": "已形成向下确认，形态是回踩未站回。",
        }
    )

    def runner(command, timeout, cwd, stdin, env):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "facts": [
                        {
                            "question_id": "clarify-price-confirmation",
                            "field": "price_confirmation",
                            "value": True,
                            "explanation": "用户确认已经形成价格确认。",
                        },
                        {
                            "question_id": "clarify-price-confirmation",
                            "field": "price_confirmation_direction",
                            "value": "BEARISH",
                            "explanation": "用户说明确认方向向下。",
                        },
                        {
                            "question_id": "clarify-price-confirmation",
                            "field": "price_confirmation_type",
                            "value": "PULLBACK",
                            "explanation": "用户说明形态为回踩未站回。",
                        },
                    ],
                    "unresolved_question_ids": [],
                    "interpretation": "执行周期形成向下回踩确认。",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("TEST_CODEX_KEY", "secret")
    provider = CodexClarificationProvider(
        runner=runner,
        model_provider="test-provider",
        provider_base_url="https://provider.invalid/v1",
        provider_env_key="TEST_CODEX_KEY",
    )

    proposal = provider.interpret(price_request)

    assert [fact.field for fact in proposal.facts] == [
        "price_confirmation",
        "price_confirmation_direction",
        "price_confirmation_type",
    ]


def test_clarification_prompt_defines_strategy_enum_mappings() -> None:
    prompt = render_clarification_prompt(request())

    assert "LONG_BUILD_SHORT_COVER" in prompt
    assert "SHORT_BUILD_LONG_EXIT" in prompt
    assert "POSITION_BUILDING" in prompt
    assert "POSITION_LIQUIDATION" in prompt
    assert "多头减仓" in prompt
    assert "price_confirmation_direction" in prompt
    assert "PULLBACK" in prompt
    assert "price_confirmation: true 或 false" in prompt
    assert "open_interest_change: 只能输出数值" in prompt
    assert "拆成三个独立 fact" in prompt
