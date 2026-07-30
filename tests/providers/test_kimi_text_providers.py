from trading_agent.clarification.models import ClarificationQuestion
from trading_agent.conversation.models import ConversationRequest
from trading_agent.providers.base import ClarificationRequest
from trading_agent.providers.kimi_text import (
    KimiClarificationProvider,
    KimiConversationProvider,
)


class FakeAcpClient:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, list[object]]] = []

    def complete(self, prompt: str, *, image_paths=()) -> str:
        self.calls.append((prompt, list(image_paths)))
        return self.output


def conversation_request() -> ConversationRequest:
    return ConversationRequest(
        case_id="case-1",
        source_analysis_id="analysis-1",
        user_message="为什么等待？",
        strategy_manifest={"strategy_id": "structure_confirmation"},
        decision={"action": "WAIT"},
        milestones=[],
        rendered={"summary": "等待"},
    )


def test_kimi_conversation_uses_selected_model_and_strict_json() -> None:
    client = FakeAcpClient(
        '{"answer":"因为价格确认步骤尚未成立。",'
        '"suggested_questions":["缺少什么确认？"]}'
    )

    reply = KimiConversationProvider(
        model="kimi-k3",
        client=client,
    ).reply(conversation_request())

    assert reply.provider == "kimi"
    assert reply.model == "kimi-k3"
    assert reply.answer == "因为价格确认步骤尚未成立。"
    assert len(client.calls) == 1
    assert client.calls[0][1] == []
    assert "为什么等待？" in client.calls[0][0]


def test_kimi_clarification_stays_within_open_questions() -> None:
    question = ClarificationQuestion(
        question_id="q-1",
        field="price_confirmation",
        milestone_number=7,
        uncertainty="是否突破",
        question="价格是否完成突破？",
        answer_examples=["是"],
        blocking_issues=["价格确认未知"],
        allowed_fact_fields=["price_confirmation"],
    )

    client = FakeAcpClient(
        '{"facts":[{"question_id":"q-1","field":"price_confirmation",'
        '"value":true,"explanation":"用户确认已经突破。"}],'
        '"unresolved_question_ids":[],"interpretation":"价格已经完成突破。"}'
    )

    proposal = KimiClarificationProvider(
        model="kimi-k3",
        client=client,
    ).interpret(
        ClarificationRequest(
            clarification_id="clarification-1",
            case_id="case-1",
            source_analysis_id="analysis-1",
            user_message="是，已经突破。",
            questions=[question],
            evidence_summary="第 7 步等待价格确认。",
        )
    )

    assert proposal.provider == "kimi"
    assert proposal.model == "kimi-k3"
    assert proposal.facts[0].field == "price_confirmation"
    assert proposal.facts[0].resolves_blockers == ["价格确认未知"]
    assert len(client.calls) == 1
