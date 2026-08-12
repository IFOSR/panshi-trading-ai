"""Order service."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from trading_agent.db.models import OrderRecord
from trading_agent.entitlement.service import EntitlementService
from trading_agent.order.models import OrderCreateRequest, OrderResponse


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_order(
        self,
        user_id: str,
        request: OrderCreateRequest,
    ) -> OrderResponse:
        # Pricing table (in fen, 1 CNY = 100 fen)
        pricing_map = {
            "free": 0,
            "onetime": {"default": 299900},
            "subscription": {
                "monthly": 9900,
                "yearly": 89900,
            },
        }
        amount = 0
        if request.pricing_type == "onetime":
            amount = pricing_map["onetime"]["default"]
        elif request.pricing_type == "subscription":
            amount = pricing_map["subscription"].get(
                request.subscription_period or "monthly", 9900,
            )

        record = OrderRecord(
            order_id=str(uuid4()),
            user_id=user_id,
            strategy_id=request.strategy_id,
            version=request.version,
            pricing_type=request.pricing_type,
            subscription_period=request.subscription_period,
            amount=amount,
            currency="CNY",
            status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return OrderResponse(
            order_id=record.order_id,
            user_id=record.user_id,
            strategy_id=record.strategy_id,
            version=record.version,
            pricing_type=record.pricing_type,
            subscription_period=record.subscription_period,
            amount=record.amount,
            currency=record.currency,
            status=record.status,
            created_at=record.created_at,
        )

    def mark_paid(self, order_id: str) -> OrderResponse:
        record = self.session.get(OrderRecord, order_id)
        if record is None:
            raise ValueError(f"order {order_id} not found")
        record.status = "paid"
        record.paid_at = datetime.now(timezone.utc)

        # Calculate subscription expiry
        if record.pricing_type == "subscription":
            delta = (
                timedelta(days=365)
                if record.subscription_period == "yearly"
                else timedelta(days=30)
            )
            record.expires_at = datetime.now(timezone.utc) + delta

        # Grant entitlement after payment
        EntitlementService(self.session).grant_access(
            user_id=record.user_id,
            strategy_id=record.strategy_id,
            version=record.version,
            access_type=record.pricing_type,
            order_id=record.order_id,
            expires_at=record.expires_at,
        )

        self.session.flush()
        return self._to_response(record)

    def list_orders(self, user_id: str) -> list[OrderResponse]:
        records = (
            self.session.query(OrderRecord)
            .filter(OrderRecord.user_id == user_id)
            .order_by(OrderRecord.created_at.desc())
            .limit(50)
            .all()
        )
        return [self._to_response(r) for r in records]

    def refund(self, order_id: str, reason: str) -> OrderResponse:
        record = self.session.get(OrderRecord, order_id)
        if record is None:
            raise ValueError(f"order {order_id} not found")
        record.status = "refunded"
        record.refund_reason = reason
        self.session.flush()
        return self._to_response(record)

    @staticmethod
    def _to_response(record: OrderRecord) -> OrderResponse:
        return OrderResponse(
            order_id=record.order_id,
            user_id=record.user_id,
            strategy_id=record.strategy_id,
            version=record.version,
            pricing_type=record.pricing_type,
            subscription_period=record.subscription_period,
            amount=record.amount,
            currency=record.currency,
            status=record.status,
            paid_at=record.paid_at,
            created_at=record.created_at,
            refund_reason=record.refund_reason,
        )
