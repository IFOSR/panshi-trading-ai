"""Strategy store service - core business logic."""

from sqlalchemy.orm import Session

from trading_agent.performance.tracker import PerformanceTracker
from trading_agent.store.models import (
    RecentPerformancePreview,
    StrategyCard,
    StrategyDetail,
    StrategyPricingInfo,
)
from trading_agent.store.repository import StoreRepository


class StrategyStoreService:
    def __init__(self, session: Session) -> None:
        self.repo = StoreRepository(session)
        self.tracker = PerformanceTracker(session)

    def list_strategies(self) -> list[StrategyCard]:
        records = self.repo.list_strategies()
        cards: list[StrategyCard] = []
        for record in records:
            version = self.repo.get_latest_version(record.strategy_id)
            pricing = None
            if version:
                pricing = StrategyPricingInfo(
                    type=version.pricing_type,
                    monthly_price=version.monthly_price,
                    yearly_price=version.yearly_price,
                    lifetime_price=version.lifetime_price,
                )

            # Get recent performance summary
            ver = version.version if version else "unknown"
            summary = self.tracker.get_summary(record.strategy_id, ver)
            perf = None
            if summary:
                perf = RecentPerformancePreview(
                    period="近3个月",
                    total_return=summary.total_return,
                    signal_count=summary.signal_count,
                    win_rate=summary.win_rate,
                    max_drawdown=summary.max_drawdown,
                )

            cards.append(
                StrategyCard(
                    strategy_id=record.strategy_id,
                    version=ver,
                    display_name=record.display_name,
                    category=record.category,
                    supported_markets=record.supported_markets or [],
                    supported_timeframes=record.supported_timeframes or [],
                    pricing=pricing,
                    recent_performance=perf,
                )
            )
        return cards

    def get_strategy_detail(
        self, strategy_id: str, version: str | None = None,
    ) -> StrategyDetail | None:
        record = self.repo.get_strategy(strategy_id)
        if record is None:
            return None

        ver_record = (
            self.repo.get_version(strategy_id, version)
            if version
            else self.repo.get_latest_version(strategy_id)
        )
        ver = ver_record.version if ver_record else "unknown"
        pricing = None
        if ver_record:
            pricing = StrategyPricingInfo(
                type=ver_record.pricing_type,
                monthly_price=ver_record.monthly_price,
                yearly_price=ver_record.yearly_price,
                lifetime_price=ver_record.lifetime_price,
            )

        summary = self.tracker.get_summary(strategy_id, ver)

        return StrategyDetail(
            strategy_id=record.strategy_id,
            version=ver,
            display_name=record.display_name,
            description=record.description,
            category=record.category,
            status=record.status,
            supported_markets=record.supported_markets or [],
            supported_timeframes=record.supported_timeframes or [],
            pricing=pricing,
            recent_performance=summary,
        )
