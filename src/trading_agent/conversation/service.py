from collections.abc import Mapping

from trading_agent.conversation.models import (
    ConversationReply,
    ConversationRequest,
)
from trading_agent.providers.base import ConversationProvider


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in value if isinstance(item, Mapping)]


class ConversationService:
    def __init__(self, provider: ConversationProvider) -> None:
        self.provider = provider

    def reply(
        self,
        *,
        case_id: str,
        analysis: Mapping[str, object],
        message: str,
    ) -> ConversationReply:
        return self.provider.reply(
            ConversationRequest(
                case_id=case_id,
                source_analysis_id=str(analysis["analysis_id"]),
                user_message=message,
                strategy_manifest=_mapping(
                    analysis.get("strategy_manifest", {})
                ),
                decision=_mapping(analysis.get("decision", {})),
                milestones=_mapping_list(analysis.get("milestones", [])),
                rendered=_mapping(analysis.get("rendered", {})),
            )
        )
