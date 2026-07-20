from dataclasses import dataclass
from datetime import date, datetime
from typing import Collection
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class SessionProfile:
    exchange: str
    has_night_session: bool = True


def resolve_trading_date(
    timestamp: datetime,
    open_dates: Collection[date],
    session_profile: SessionProfile | None = None,
) -> date:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    timestamp = timestamp.astimezone(SHANGHAI)
    calendar_date = timestamp.date()
    ordered = sorted(open_dates)

    if timestamp.hour >= 20:
        if session_profile is not None and not session_profile.has_night_session:
            raise ValueError("product has no night session")
        for candidate in ordered:
            if candidate > calendar_date:
                return candidate
        raise ValueError("no next open trading date is available")

    if calendar_date not in open_dates:
        raise ValueError(f"{calendar_date.isoformat()} is not an open trading date")
    return calendar_date
