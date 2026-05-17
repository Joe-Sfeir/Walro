from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from sqlite3 import Connection, Row

from .parser import ParsedTransaction
from .utils import now_local, today_local


class WalroError(ValueError):
    pass


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def last_day_of_month(d: date) -> date:
    _, days = calendar.monthrange(d.year, d.month)
    return date(d.year, d.month, days)


def first_day_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def inclusive_days(start: date, end: date) -> int:
    return (end - start).days + 1


def active_budget(conn: Connection) -> Row | None:
    return conn.execute(
        "SELECT * FROM budgets WHERE active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()


def deactivate_active_budgets(conn: Connection) -> None:
    conn.execute("UPDATE budgets SET active = 0 WHERE active = 1")


def get_setting(conn: Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def set_fx_rate(conn: Connection, currency: str, rate: float) -> None:
    currency = currency.lower()
    if currency == "usd":
        raise WalroError("USD is the base currency, so its rate is always 1.")
    if currency not in {"aed", "lbp"}:
        raise WalroError("Supported currencies are USD, AED, and LBP.")
    if rate <= 0:
        raise WalroError("Rate must be greater than 0.")
    set_setting(conn, f"fx_{currency}", str(rate))


def get_fx_rate(conn: Connection, currency: str) -> float:
    currency = currency.lower()
    if currency == "usd":
        return 1.0
    raw = get_setting(conn, f"fx_{currency}")
    if raw is None:
        raise WalroError(f"No rate set for {currency.upper()}. Use /setrate {currency} RATE first.")
    return float(raw)


def to_usd(conn: Connection, amount: float, currency: str) -> float:
    rate = get_fx_rate(conn, currency)
    return amount / rate


def category_exists(conn: Connection, code: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM categories WHERE code = ? AND active = 1", (code.lower(),)
    ).fetchone()
    return row is not None


def add_category(conn: Connection, code: str, name: str) -> None:
    code = code.lower().strip()
    name = name.strip().lower()
    if not code or not name:
        raise WalroError("Use /addcategory code name. Example: /addcategory e entertainment")
    if len(code) > 12:
        raise WalroError("Category code should be short, like e or bills.")
    conn.execute(
        "INSERT INTO categories (code, name, active) VALUES (?, ?, 1) "
        "ON CONFLICT(code) DO UPDATE SET name = excluded.name, active = 1",
        (code, name),
    )


def list_categories(conn: Connection) -> list[Row]:
    return conn.execute(
        "SELECT code, name FROM categories WHERE active = 1 ORDER BY code"
    ).fetchall()


def start_fixed_budget(conn: Connection, total_usd: float, days: int, today: date | None = None) -> Row:
    if total_usd <= 0:
        raise WalroError("Budget amount must be greater than 0.")
    if days <= 0:
        raise WalroError("Days must be greater than 0.")
    today = today or today_local()
    end = today + timedelta(days=days - 1)
    daily = total_usd / days
    deactivate_active_budgets(conn)
    cur = conn.execute(
        """
        INSERT INTO budgets
        (mode, total_budget_usd, daily_allowance_usd, starting_surplus_usd, start_date, end_date, active, created_at)
        VALUES ('fixed', ?, ?, 0, ?, ?, 1, ?)
        """,
        (total_usd, daily, today.isoformat(), end.isoformat(), iso_now()),
    )
    return conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()


def start_monthly_budget(conn: Connection, total_usd: float, today: date | None = None) -> Row:
    if total_usd <= 0:
        raise WalroError("Budget amount must be greater than 0.")
    today = today or today_local()
    end = last_day_of_month(today)
    days = inclusive_days(today, end)
    daily = total_usd / days
    deactivate_active_budgets(conn)
    cur = conn.execute(
        """
        INSERT INTO budgets
        (mode, total_budget_usd, daily_allowance_usd, starting_surplus_usd, start_date, end_date, active, created_at)
        VALUES ('monthly', ?, ?, 0, ?, ?, 1, ?)
        """,
        (total_usd, daily, today.isoformat(), end.isoformat(), iso_now()),
    )
    return conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()


def ensure_monthly_rollover(conn: Connection, today: date | None = None) -> Row | None:
    """If a monthly budget ended, create the next monthly cycle and carry surplus forward."""
    today = today or today_local()
    budget = active_budget(conn)
    if not budget:
        return None
    if budget["mode"] != "monthly":
        return budget

    end = parse_date(budget["end_date"])
    if today <= end:
        return budget

    old_summary = calculate_summary(conn, budget, reference_date=end + timedelta(days=1))
    carry = old_summary["surplus_usd"]

    deactivate_active_budgets(conn)
    start = first_day_of_month(today)
    new_end = last_day_of_month(today)
    days = inclusive_days(start, new_end)
    daily = budget["total_budget_usd"] / days
    cur = conn.execute(
        """
        INSERT INTO budgets
        (mode, total_budget_usd, daily_allowance_usd, starting_surplus_usd, start_date, end_date, active, created_at)
        VALUES ('monthly', ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            budget["total_budget_usd"],
            daily,
            carry,
            start.isoformat(),
            new_end.isoformat(),
            iso_now(),
        ),
    )
    return conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()


def require_active_budget(conn: Connection) -> Row:
    budget = ensure_monthly_rollover(conn)
    if not budget:
        raise WalroError("No active budget. Start one with /startbudget 3000 25 or /startmonth 3000.")
    return budget


def _sum_amount(conn: Connection, budget_id: int, tx_type: str, start: date | None = None, end: date | None = None) -> float:
    query = "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM transactions WHERE budget_id = ? AND type = ?"
    params: list[object] = [budget_id, tx_type]
    if start is not None:
        query += " AND tx_date >= ?"
        params.append(start.isoformat())
    if end is not None:
        query += " AND tx_date <= ?"
        params.append(end.isoformat())
    row = conn.execute(query, params).fetchone()
    return float(row["total"] or 0)


def _income_rows(conn: Connection, budget_id: int) -> list[Row]:
    return conn.execute(
        """
        SELECT tx_date, amount_usd
        FROM transactions
        WHERE budget_id = ? AND type = 'income'
        ORDER BY tx_date ASC, created_at ASC, id ASC
        """,
        (budget_id,),
    ).fetchall()


def _daily_allowance_for_day(conn: Connection, budget: Row, day: date, income_rows: list[Row] | None = None) -> float:
    """
    Initial budget is split over the original period.
    Each +income is split only over the remaining days from the income date onward.
    This avoids retroactively changing past days.
    """
    end = parse_date(budget["end_date"])
    daily = float(budget["daily_allowance_usd"])
    rows = income_rows if income_rows is not None else _income_rows(conn, budget["id"])

    for row in rows:
        income_day = parse_date(row["tx_date"])
        if income_day <= day <= end:
            days_from_income = inclusive_days(income_day, end)
            daily += float(row["amount_usd"]) / days_from_income
    return daily


def _allowance_accrued(conn: Connection, budget: Row, start: date, end: date, income_rows: list[Row] | None = None) -> float:
    if end < start:
        return 0.0
    total = 0.0
    d = start
    rows = income_rows if income_rows is not None else _income_rows(conn, budget["id"])
    while d <= end:
        total += _daily_allowance_for_day(conn, budget, d, rows)
        d += timedelta(days=1)
    return total


def calculate_summary(conn: Connection, budget: Row, reference_date: date | None = None) -> dict[str, float | int | bool | str]:
    today = reference_date or today_local()
    start = parse_date(budget["start_date"])
    end = parse_date(budget["end_date"])
    income_rows = _income_rows(conn, budget["id"])
    income = sum(float(row["amount_usd"]) for row in income_rows)

    today_active = start <= today <= end
    daily = _daily_allowance_for_day(conn, budget, min(max(today, start), end), income_rows)

    closed_end = min(today - timedelta(days=1), end)
    closed_days = 0
    normal_spent_closed = 0.0
    closed_allowance = 0.0
    if closed_end >= start:
        closed_days = inclusive_days(start, closed_end)
        normal_spent_closed = _sum_amount(conn, budget["id"], "expense", start, closed_end)
        closed_allowance = _allowance_accrued(conn, budget, start, closed_end, income_rows)

    closed_surplus = closed_allowance - normal_spent_closed
    surplus_expense = _sum_amount(conn, budget["id"], "surplus_expense")
    surplus = float(budget["starting_surplus_usd"]) + closed_surplus - surplus_expense

    today_spent = _sum_amount(conn, budget["id"], "expense", today, today) if today_active else 0.0
    today_remaining = daily - today_spent if today_active else 0.0
    days_left = inclusive_days(today, end) if today <= end else 0
    total_days = inclusive_days(start, end)
    base_budget = float(budget["total_budget_usd"])

    return {
        "budget_id": budget["id"],
        "mode": budget["mode"],
        "base_budget_usd": base_budget,
        "total_budget_usd": base_budget + income,
        "daily_allowance_usd": daily,
        "starting_surplus_usd": float(budget["starting_surplus_usd"]),
        "start_date": budget["start_date"],
        "end_date": budget["end_date"],
        "total_days": total_days,
        "closed_days": closed_days,
        "days_left": days_left,
        "today_active": today_active,
        "today_spent_usd": today_spent,
        "today_remaining_usd": today_remaining,
        "surplus_usd": surplus,
        "income_usd": income,
        "surplus_expense_usd": surplus_expense,
        "closed_surplus_usd": closed_surplus,
    }


def log_transaction(conn: Connection, parsed: ParsedTransaction) -> tuple[Row, Row, dict]:
    budget = require_active_budget(conn)
    today = today_local()
    start = parse_date(budget["start_date"])
    end = parse_date(budget["end_date"])

    if not (start <= today <= end):
        raise WalroError("This budget period has ended. Start a new budget before logging expenses.")

    if parsed.category_code and not category_exists(conn, parsed.category_code):
        raise WalroError(
            f"Unknown category '{parsed.category_code}'. Add it with /addcategory {parsed.category_code} name."
        )

    amount_usd = to_usd(conn, parsed.amount, parsed.currency)
    cur = conn.execute(
        """
        INSERT INTO transactions
        (budget_id, created_at, tx_date, type, amount_usd, original_amount, currency, category_code, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            budget["id"],
            iso_now(),
            today.isoformat(),
            parsed.type,
            amount_usd,
            parsed.amount,
            parsed.currency.lower(),
            parsed.category_code,
            parsed.comment,
        ),
    )
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)).fetchone()
    summary = calculate_summary(conn, budget)
    return tx, budget, summary


def get_history(conn: Connection, limit: int = 10) -> list[Row]:
    budget = require_active_budget(conn)
    limit = max(1, min(limit, 50))
    return conn.execute(
        """
        SELECT * FROM transactions
        WHERE budget_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (budget["id"], limit),
    ).fetchall()


def undo_last(conn: Connection) -> Row:
    budget = require_active_budget(conn)
    tx = conn.execute(
        """
        SELECT * FROM transactions
        WHERE budget_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (budget["id"],),
    ).fetchone()
    if not tx:
        raise WalroError("No transaction to undo.")
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx["id"],))
    return tx


def category_breakdown_today(conn: Connection, budget_id: int, day: date | None = None) -> list[Row]:
    day = day or today_local()
    return conn.execute(
        """
        SELECT COALESCE(category_code, '-') AS category_code,
               COALESCE(SUM(amount_usd), 0) AS total
        FROM transactions
        WHERE budget_id = ? AND tx_date = ? AND type = 'expense'
        GROUP BY category_code
        ORDER BY total DESC
        """,
        (budget_id, day.isoformat()),
    ).fetchall()
