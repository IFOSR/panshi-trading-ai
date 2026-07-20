from datetime import date, datetime
from typing import Collection


def resolve_trading_date(
    timestamp: datetime,
    open_dates: Collection[date],
) -> date:
    calendar_date = timestamp.date()
    ordered = sorted(open_dates)

    if timestamp.hour >= 20:
        for candidate in ordered:
            if candidate > calendar_date:
                return candidate
        raise ValueError("no next open trading date is available")

    if calendar_date not in open_dates:
        raise ValueError(f"{calendar_date.isoformat()} is not an open trading date")
    return calendar_date

