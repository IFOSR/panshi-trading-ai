"""Strategy store data access."""

from sqlalchemy.orm import Session

from trading_agent.db.models import StrategyRecord, StrategyVersionRecord


class StoreRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_strategies(self) -> list[StrategyRecord]:
        return (
            self.session.query(StrategyRecord)
            .filter(StrategyRecord.status != "disabled")
            .all()
        )

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        return self.session.get(StrategyRecord, strategy_id)

    def get_latest_version(self, strategy_id: str) -> StrategyVersionRecord | None:
        return (
            self.session.query(StrategyVersionRecord)
            .filter(
                StrategyVersionRecord.strategy_id == strategy_id,
                StrategyVersionRecord.status != "disabled",
            )
            .order_by(StrategyVersionRecord.created_at.desc())
            .first()
        )

    def get_version(
        self, strategy_id: str, version: str,
    ) -> StrategyVersionRecord | None:
        version_id = f"{strategy_id}@{version}"
        return self.session.get(StrategyVersionRecord, version_id)
