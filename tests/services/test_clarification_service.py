from trading_agent.clarification.models import ClarificationQuestion
from trading_agent.services.clarification import ClarificationService
from trading_agent.strategies.contracts import StrategyManifest
from trading_agent.strategies.registry import StrategyRegistry
from trading_agent.strategies.structure_confirmation import (
    StructureConfirmationStrategy,
)
from trading_agent.workflows.analysis import AnalysisWorkflow


class Provider:
    def interpret(self, request):
        raise AssertionError("provider is not needed for question discovery")


class CustomClarificationStrategy(StructureConfirmationStrategy):
    manifest = StrategyManifest(
        **{
            **StructureConfirmationStrategy.manifest.model_dump(),
            "strategy_id": "custom_clarification",
            "version": "2.0.0",
            "display_name": "自定义澄清策略",
        }
    )

    def clarification_questions(self, analysis):
        return [
            ClarificationQuestion(
                question_id="clarify-custom-step",
                field="custom_regime",
                allowed_fact_fields=["custom_regime"],
                milestone_number=12,
                uncertainty="自定义状态未知。",
                question="请确认自定义状态。",
                answer_examples=["状态 A", "状态 B"],
                blocking_issues=["CUSTOM_STATE_MISSING"],
            )
        ]


def test_clarification_service_uses_the_injected_strategy_registry() -> None:
    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(StructureConfirmationStrategy())
    registry.register(CustomClarificationStrategy())
    service = ClarificationService(
        Provider(),
        workflow=AnalysisWorkflow(strategy_registry=registry),
    )

    questions = service.questions(
        {
            "analysis_id": "analysis-1",
            "strategy_manifest": {
                "strategy_id": "custom_clarification",
                "version": "2.0.0",
            },
            "milestones": [],
        }
    )

    assert [question.field for question in questions] == ["custom_regime"]
    assert questions[0].milestone_number == 12
