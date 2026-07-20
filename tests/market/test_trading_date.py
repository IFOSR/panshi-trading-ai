from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from trading_agent.market.calendar import SessionProfile, resolve_trading_date


OPEN_DATES = {
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
}


def test_friday_night_session_maps_to_next_open_trading_date() -> None:
    timestamp = datetime(2026, 7, 17, 21, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert resolve_trading_date(timestamp, OPEN_DATES) == date(2026, 7, 20)


def test_day_session_keeps_current_open_trading_date() -> None:
    timestamp = datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert resolve_trading_date(timestamp, OPEN_DATES) == date(2026, 7, 20)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        resolve_trading_date(datetime(2026, 7, 20, 10, 0), OPEN_DATES)


def test_product_without_night_session_rejects_night_timestamp() -> None:
    timestamp = datetime(2026, 7, 17, 21, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    with pytest.raises(ValueError, match="night session"):
        resolve_trading_date(
            timestamp,
            OPEN_DATES,
            session_profile=SessionProfile(exchange="CFFEX", has_night_session=False),
        )
