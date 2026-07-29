import pytest

from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult, StrategyEvaluation
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyManifest,
)
from trading_agent.strategies.structure_confirmation import (
    StructureConfirmationStrategy,
)


def test_generic_strategy_evaluation_accepts_a_dynamic_milestone_count() -> None:
    evaluation = StrategyEvaluation(
        steps=[
            MilestoneResult(
                number=1,
                code="INPUT",
                status=MilestoneStatus.CONFIRMED,
                result="READY",
            ),
            MilestoneResult(
                number=2,
                code="SIGNAL",
                status=MilestoneStatus.CANDIDATE,
                result="WATCH",
            ),
            MilestoneResult(
                number=3,
                code="OUTPUT",
                status=MilestoneStatus.CONFIRMED,
                result="WAIT",
            ),
        ]
    )

    assert [step.number for step in evaluation.steps] == [1, 2, 3]


def test_generic_strategy_evaluation_rejects_duplicate_sequences() -> None:
    with pytest.raises(ValueError, match="unique contiguous"):
        StrategyEvaluation(
            steps=[
                MilestoneResult(
                    number=1,
                    code="INPUT",
                    status=MilestoneStatus.CONFIRMED,
                    result="READY",
                ),
                MilestoneResult(
                    number=1,
                    code="OUTPUT",
                    status=MilestoneStatus.CONFIRMED,
                    result="WAIT",
                ),
            ]
        )


def test_strategy_manifest_exposes_product_metadata_without_ui_code() -> None:
    manifest = StrategyManifest(
        strategy_id="fixture_strategy",
        display_name="Fixture Strategy",
        version="1.2.3",
        status="test",
        entrypoint="fixtures:Strategy",
        supported_markets=["CN_FUTURES"],
        supported_timeframes=["1d"],
        process_label="Fixture Process",
        risk_profile_id="risk-v1",
    )

    assert manifest.strategy_id == "fixture_strategy"
    assert manifest.input_schema_version == "strategy-input-v1"
    assert manifest.output_schema_version == "strategy-result-v1"


def test_default_strategy_owns_human_readable_milestone_titles() -> None:
    run = StructureConfirmationStrategy().evaluate(
        StrategyInputSnapshot(
            facts=StrategyContext(contract="cf2609").model_dump(mode="json"),
            position="UNKNOWN",
        )
    )

    assert [item.title for item in run.milestones] == [
        "数据有效性",
        "市场状态",
        "策略许可",
        "价格位置",
        "量仓行为",
        "动量",
        "价格确认",
    ]
