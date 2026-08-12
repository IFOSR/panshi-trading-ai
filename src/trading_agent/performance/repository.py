"""Performance data repository."""

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from trading_agent.db.models import PerformanceSignalRecord, PerformanceSummaryRecord


class PerformanceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_signal(self, record: PerformanceSignalRecord) -> PerformanceSignalRecord:
        self.session.add(record)
        self.session.flush()
        return record

    def save_summary(
        self, record: PerformanceSummaryRecord,
    ) -> PerformanceSummaryRecord:
        existing = self.session.get(PerformanceSummaryRecord, record.summary_id)
        if existing:
            existing.total_return = record.total_return
            existing.max_drawdown = record.max_drawdown
            existing.signal_count = record.signal_count
            existing.win_count = record.win_count
            existing.loss_count = record.loss_count
            existing.win_rate = record.win_rate
            existing.equity_curve = record.equity_curve
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        self.session.add(record)
        self.session.flush()
        return record

    def get_summary(
        self,
        strategy_id: str,
        version: str,
        period: str = "last_3_months",
    ) -> PerformanceSummaryRecord | None:
        summary_id = f"{strategy_id}@{version}@{period}"
        return self.session.get(PerformanceSummaryRecord, summary_id)

    def list_signals(
        self,
        strategy_id: str,
        version: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[PerformanceSignalRecord]:
        query = self.session.query(PerformanceSignalRecord).filter(
            PerformanceSignalRecord.strategy_id == strategy_id,
            PerformanceSignalRecord.version == version,
        )
        if start_date:
            query = query.filter(
                PerformanceSignalRecord.signal_date >= start_date,
            )
        if end_date:
            query = query.filter(
                PerformanceSignalRecord.signal_date <= end_date,
            )
        return query.order_by(
            PerformanceSignalRecord.signal_date.desc(),
        ).limit(limit).all()
