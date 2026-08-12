"""Performance tracker - computes strategy performance data."""

from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from trading_agent.db.models import PerformanceSignalRecord, PerformanceSummaryRecord
from trading_agent.performance.models import (
    PerformanceSignalItem,
    PerformanceSummaryResponse,
)
from trading_agent.performance.repository import PerformanceRepository
from trading_agent.strategies.contracts import PerformanceTrack, StrategyPlugin


class PerformanceTracker:
    def __init__(self, session: Session) -> None:
        self.repo = PerformanceRepository(session)

    def track_strategy(
        self,
        plugin: StrategyPlugin,
        start_date: date,
        end_date: date,
        market_data: dict | None = None,
    ) -> PerformanceSummaryResponse:
        """Run strategy track_performance and persist results."""
        manifest = plugin.manifest
        period = "last_3_months"

        track: PerformanceTrack = plugin.track_performance(
            start_date=start_date,
            end_date=end_date,
            market_data=market_data,
        )

        # Save signals
        signals: list[PerformanceSignalItem] = []
        for sig in track.signals:
            record = PerformanceSignalRecord(
                signal_id=str(uuid4()),
                strategy_id=manifest.strategy_id,
                version=manifest.version,
                contract=sig.get("contract", "UNKNOWN"),
                signal_date=sig.get("signal_date", start_date),
                direction=sig.get("direction", "FLAT"),
                entry_price=sig.get("entry_price"),
                exit_price=sig.get("exit_price"),
                return_pct=sig.get("return_pct"),
                status=sig.get("status", "open"),
                closed_date=sig.get("closed_date"),
                evidence=sig.get("evidence"),
            )
            self.repo.save_signal(record)
            signals.append(
                PerformanceSignalItem(
                    contract=record.contract,
                    signal_date=record.signal_date,
                    direction=record.direction,
                    entry_price=record.entry_price,
                    exit_price=record.exit_price,
                    return_pct=record.return_pct,
                    status=record.status,
                    closed_date=record.closed_date,
                    evidence=record.evidence,
                )
            )

        # Compute summary
        summary = track.summary
        total_return = summary.get("total_return", 0.0)
        signal_count = len(track.signals)
        win_count = summary.get("win_count", 0)
        loss_count = summary.get("loss_count", 0)
        win_rate = summary.get("win_rate", 0.0)
        max_drawdown = summary.get("max_drawdown", 0.0)
        equity_curve = summary.get("equity_curve", [])

        summary_record = PerformanceSummaryRecord(
            summary_id=f"{manifest.strategy_id}@{manifest.version}@{period}",
            strategy_id=manifest.strategy_id,
            version=manifest.version,
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            max_drawdown=max_drawdown,
            signal_count=signal_count,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=win_rate,
            equity_curve=equity_curve,
        )
        self.repo.save_summary(summary_record)

        return PerformanceSummaryResponse(
            strategy_id=manifest.strategy_id,
            version=manifest.version,
            period="近3个月",
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            max_drawdown=max_drawdown,
            signal_count=signal_count,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=win_rate,
            equity_curve=equity_curve,
            signals=signals,
        )

    def get_summary(
        self,
        strategy_id: str,
        version: str,
        period: str = "last_3_months",
    ) -> PerformanceSummaryResponse | None:
        """Retrieve pre-computed performance summary."""
        record = self.repo.get_summary(strategy_id, version, period)
        if record is None:
            return None

        signals = self.repo.list_signals(
            strategy_id,
            version,
            start_date=record.start_date,
            end_date=record.end_date,
        )
        return PerformanceSummaryResponse(
            strategy_id=record.strategy_id,
            version=record.version,
            period="近3个月",
            start_date=record.start_date,
            end_date=record.end_date,
            total_return=record.total_return,
            max_drawdown=record.max_drawdown,
            signal_count=record.signal_count,
            win_count=record.win_count,
            loss_count=record.loss_count,
            win_rate=record.win_rate,
            equity_curve=record.equity_curve,
            signals=[
                PerformanceSignalItem(
                    contract=s.contract,
                    signal_date=s.signal_date,
                    direction=s.direction,
                    entry_price=s.entry_price,
                    exit_price=s.exit_price,
                    return_pct=s.return_pct,
                    status=s.status,
                    closed_date=s.closed_date,
                    evidence=s.evidence,
                )
                for s in signals
            ],
        )
