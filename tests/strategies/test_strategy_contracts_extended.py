"""TDD tests for Phase 1: strategy contract extensions."""

from datetime import date

import pytest
from pydantic import ValidationError

from trading_agent.strategies.contracts import (
    DataRequirement,
    FactRequirement,
    PerformanceConfig,
    PerformanceTrack,
    StrategyManifest,
    StrategyPricing,
)


class TestStrategyPricing:
    def test_free_pricing_is_valid(self) -> None:
        """免费定价模型有效。"""
        pricing = StrategyPricing(type="free")
        assert pricing.type == "free"
        assert pricing.monthly_price is None
        assert pricing.yearly_price is None
        assert pricing.lifetime_price is None

    def test_subscription_pricing_is_valid(self) -> None:
        """订阅定价模型有效。"""
        pricing = StrategyPricing(
            type="subscription",
            monthly_price=9900,
            yearly_price=89900,
        )
        assert pricing.type == "subscription"
        assert pricing.monthly_price == 9900
        assert pricing.yearly_price == 89900

    def test_onetime_pricing_is_valid(self) -> None:
        """单次购买定价模型有效。"""
        pricing = StrategyPricing(
            type="onetime",
            lifetime_price=299900,
        )
        assert pricing.type == "onetime"
        assert pricing.lifetime_price == 299900

    def test_pricing_type_must_be_valid(self) -> None:
        """定价类型必须是有效值。"""
        with pytest.raises(ValidationError):
            StrategyPricing(type="invalid")


class TestPerformanceConfig:
    def test_default_config(self) -> None:
        """默认表现配置有效。"""
        config = PerformanceConfig()
        assert config.track_enabled is True
        assert config.history_days == 90
        assert config.update_cron == "0 16 * * 1-5"

    def test_custom_config(self) -> None:
        """自定义表现配置有效。"""
        config = PerformanceConfig(
            track_enabled=False,
            history_days=180,
        )
        assert config.track_enabled is False
        assert config.history_days == 180


class TestPerformanceTrack:
    def test_validation_rejects_zero_signals(self) -> None:
        """信号列表为空的 PerformanceTrack 无效（至少需要一个信号）。"""
        with pytest.raises(ValidationError):
            PerformanceTrack(
                strategy_id="test",
                version="1.0.0",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 3, 31),
                signals=[],
                summary={},
            )

    def test_valid_performance_track(self) -> None:
        """有效的表现跟踪数据可创建。"""
        track = PerformanceTrack(
            strategy_id="test",
            version="1.0.0",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            signals=[
                {
                    "contract": "RB2610",
                    "signal_date": date(2025, 1, 15),
                    "direction": "LONG",
                    "entry_price": 3500.0,
                    "exit_price": 3550.0,
                    "return_pct": 0.014,
                    "status": "closed",
                    "closed_date": date(2025, 1, 20),
                }
            ],
            summary={
                "total_return": 0.014,
                "signal_count": 1,
                "win_rate": 1.0,
            },
        )
        assert track.strategy_id == "test"
        assert len(track.signals) == 1


class TestFactRequirement:
    def test_required_fact(self) -> None:
        """必填事实声明有效。"""
        fact = FactRequirement(
            field="contract",
            label="分析标的",
            required=True,
            source=["user_input", "attachment"],
            description="用户希望分析的具体合约或品种",
        )
        assert fact.field == "contract"
        assert fact.required is True

    def test_optional_fact_with_default(self) -> None:
        """可选事实声明（带默认值）有效。"""
        fact = FactRequirement(
            field="timeframe",
            label="分析周期",
            required=False,
            default="1d",
            source=["user_input", "system_default"],
        )
        assert fact.required is False
        assert fact.default == "1d"


class TestDataRequirement:
    def test_ohlcv_data_requirement(self) -> None:
        """OHLCV 数据需求有效。"""
        req = DataRequirement(
            type="ohlcv",
            timeframe="1d",
            length=120,
        )
        assert req.type == "ohlcv"
        assert req.timeframe == "1d"
        assert req.length == 120

    def test_events_data_requirement(self) -> None:
        """事件数据需求有效。"""
        req = DataRequirement(
            type="events",
            categories=["macro", "earnings"],
        )
        assert req.type == "events"
        assert req.categories == ["macro", "earnings"]


class TestStrategyManifestExtensions:
    def test_manifest_with_pricing(self) -> None:
        """策略清单可以携带定价信息。"""
        manifest = StrategyManifest(
            strategy_id="test_strategy",
            display_name="测试策略",
            version="1.0.0",
            status="stable",
            entrypoint="test.module:Test",
            supported_markets=["CN_FUTURES"],
            process_label="test",
            risk_profile_id="test-risk-v1",
            pricing=StrategyPricing(type="free"),
        )
        assert manifest.pricing is not None
        assert manifest.pricing.type == "free"

    def test_manifest_with_performance_config(self) -> None:
        """策略清单可以携带表现配置。"""
        manifest = StrategyManifest(
            strategy_id="test_strategy",
            display_name="测试策略",
            version="1.0.0",
            status="stable",
            entrypoint="test.module:Test",
            supported_markets=["CN_FUTURES"],
            process_label="test",
            risk_profile_id="test-risk-v1",
            performance_config=PerformanceConfig(history_days=60),
        )
        assert manifest.performance_config is not None
        assert manifest.performance_config.history_days == 60

    def test_manifest_without_pricing_defaults_to_none(self) -> None:
        """不带定价的策略清单，pricing 默认为 None。"""
        manifest = StrategyManifest(
            strategy_id="test_strategy",
            display_name="测试策略",
            version="1.0.0",
            status="stable",
            entrypoint="test.module:Test",
            supported_markets=["CN_FUTURES"],
            process_label="test",
            risk_profile_id="test-risk-v1",
        )
        assert manifest.pricing is None
        assert manifest.performance_config is None
