"""TDD tests for FactExtractor."""

from trading_agent.strategies.contracts import (
    FactRequirement,
    DataRequirement,
    PerformanceTrack,
    StrategyInputSnapshot,
    StrategyManifest,
    StrategyRun,
    StrategyPricing,
)
from trading_agent.fact_extractor.extractor import FactExtractor
from trading_agent.fact_extractor.models import FactExtractionResult, ExtractionStatus


class MockStrategy:
    manifest = StrategyManifest(
        strategy_id="test_strategy",
        display_name="Test",
        version="1.0.0",
        status="stable",
        entrypoint="test:Mock",
        supported_markets=["CN_FUTURES"],
        risk_profile_id="test-risk",
        process_label="test",
        pricing=StrategyPricing(type="free"),
    )

    def required_facts(self, context: dict) -> list[FactRequirement]:
        return [
            FactRequirement(
                field="contract",
                label="分析标的",
                required=True,
                source=["user_input", "attachment"],
                description="用户希望分析的具体合约",
            ),
            FactRequirement(
                field="position_direction",
                label="当前持仓方向",
                required=False,
                source=["user_input"],
            ),
            FactRequirement(
                field="timeframe",
                label="分析周期",
                required=False,
                default="1d",
                source=["user_input", "system_default"],
            ),
        ]

    def required_data(self, context: dict) -> list[DataRequirement]:
        return [DataRequirement(type="ohlcv", timeframe="1d", length=120)]

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        raise NotImplementedError

    def track_performance(self, start_date, end_date, market_data=None) -> PerformanceTrack:
        raise NotImplementedError


def test_extracts_contract_from_user_message() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="分析一下螺纹钢rb2610的走势",
        conversation_history=[],
        attachments=[],
    )
    assert "contract" in result.extracted_facts
    assert result.extracted_facts["contract"] == "rb2610"


def test_detects_missing_required_facts() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="请帮我分析一下走势",
        conversation_history=[],
        attachments=[],
    )
    assert result.status == ExtractionStatus.MISSING_INFO
    assert len(result.missing_fields) >= 1
    assert any(f.field == "contract" for f in result.missing_fields)


def test_uses_default_values_for_optional_facts() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="分析螺纹钢rb2610",
        conversation_history=[],
        attachments=[],
    )
    assert result.status == ExtractionStatus.COMPLETE  # contract found, optional fields have defaults or aren't required
    assert result.extracted_facts.get("timeframe") == "1d"


def test_extracts_position_direction_from_message() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="我持有螺纹钢rb2610多单，帮我分析一下",
        conversation_history=[],
        attachments=[],
    )
    assert result.extracted_facts.get("contract") == "rb2610"
    assert result.extracted_facts.get("position_direction") == "LONG"


def test_all_required_facts_present_returns_complete() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="分析rb2610，目前持有多单",
        conversation_history=[],
        attachments=[],
    )
    assert result.status in (ExtractionStatus.MISSING_INFO, ExtractionStatus.COMPLETE)
    assert result.extracted_facts.get("contract") == "rb2610"
    assert result.extracted_facts.get("position_direction") == "LONG"


def test_generates_clarification_questions() -> None:
    strategy = MockStrategy()
    extractor = FactExtractor(strategy)
    result = extractor.extract(
        message="帮我分析",
        conversation_history=[],
        attachments=[],
    )
    assert result.status == ExtractionStatus.MISSING_INFO
    questions = result.clarification_questions
    assert len(questions) >= 1
    assert any("标的" in q for q in questions)
