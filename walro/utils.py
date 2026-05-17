from __future__ import annotations

from datetime import date, datetime

from .config import timezone


def now_local() -> datetime:
    return datetime.now(timezone())


def today_local() -> date:
    return now_local().date()


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def signed_money(value: float) -> str:
    if value > 0:
        return f"+{money(value)}"
    if value < 0:
        return f"-{money(abs(value))}"
    return "$0.00"
