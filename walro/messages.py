from __future__ import annotations

from sqlite3 import Row

from .core import category_breakdown_today
from .utils import money, signed_money


def start_help() -> str:
    return (
        "Walro is ready.\n\n"
        "Start a budget:\n"
        "/startbudget 3000 25\n"
        "/startbudget 3000 aed 25\n"
        "/startmonth 3000\n\n"
        "Log spending:\n"
        "22 aed f daves hot chicken\n"
        "S 200 usd s headphones\n"
        "+500 usd salary\n\n"
        "Commands:\n"
        "/status, /history, /undo, /rates, /setrate, /categories, /addcategory, /whoami"
    )


def format_summary(summary: dict, breakdown: list[Row] | None = None) -> str:
    lines = [
        "Walro status",
        f"Mode: {summary['mode']}",
        f"Period: {summary['start_date']} → {summary['end_date']}",
        f"Total budget: {money(float(summary['total_budget_usd']))}",
        f"Daily allowance: {money(float(summary['daily_allowance_usd']))}",
        "",
    ]

    if summary["today_active"]:
        lines += [
            f"Today spent: {money(float(summary['today_spent_usd']))}",
            f"Today remaining: {signed_money(float(summary['today_remaining_usd']))}",
        ]
    else:
        lines.append("Today: outside this budget period")

    lines += [
        f"Surplus: {signed_money(float(summary['surplus_usd']))}",
        f"Days left: {summary['days_left']}",
    ]

    surplus = float(summary["surplus_usd"])
    days_left = int(summary["days_left"])
    daily = float(summary["daily_allowance_usd"])
    if surplus < 0 and days_left > 0:
        needed = abs(surplus) / days_left
        lines += [
            "",
            f"Recovery: leave about {money(needed)} unspent per remaining day to reach zero surplus.",
        ]
        if needed > daily:
            lines.append("That is more than your full daily allowance, so you need income or a longer recovery period.")
    elif surplus > 0:
        lines += ["", f"Buffer: you are ahead by {money(surplus)}."]

    if breakdown:
        lines += ["", "Today by category:"]
        for row in breakdown:
            lines.append(f"- {row['category_code']}: {money(float(row['total']))}")

    return "\n".join(lines)


def format_transaction_reply(tx: Row, summary: dict, category_name: str | None = None) -> str:
    original = f"{tx['original_amount']:g} {tx['currency'].upper()}"
    usd = money(float(tx["amount_usd"]))
    cat = f" [{tx['category_code']}]" if tx["category_code"] else ""

    if tx["type"] == "expense":
        return (
            f"Logged daily expense{cat}: {original} = {usd}\n"
            f"Comment: {tx['comment']}\n\n"
            f"Today remaining: {signed_money(float(summary['today_remaining_usd']))}\n"
            f"Surplus: {signed_money(float(summary['surplus_usd']))}"
        )

    if tx["type"] == "surplus_expense":
        return (
            f"Logged surplus expense{cat}: {original} = {usd}\n"
            f"Comment: {tx['comment']}\n\n"
            f"Today remaining: {signed_money(float(summary['today_remaining_usd']))}\n"
            f"Surplus: {signed_money(float(summary['surplus_usd']))}"
        )

    return (
        f"Added to budget plan: {original} = {usd}\n"
        f"Comment: {tx['comment']}\n\n"
        f"New total budget: {money(float(summary['total_budget_usd']))}\n"
        f"New daily allowance: {money(float(summary['daily_allowance_usd']))}\n"
        f"Today remaining: {signed_money(float(summary['today_remaining_usd']))}\n"
        f"Surplus: {signed_money(float(summary['surplus_usd']))}"
    )


def format_history(rows: list[Row]) -> str:
    if not rows:
        return "No transactions yet."
    lines = ["Recent transactions:"]
    for tx in rows:
        prefix = {
            "expense": "daily",
            "surplus_expense": "surplus",
            "income": "income",
        }.get(tx["type"], tx["type"])
        cat = f" {tx['category_code']}" if tx["category_code"] else ""
        lines.append(
            f"#{tx['id']} {tx['tx_date']} {prefix}{cat}: "
            f"{money(float(tx['amount_usd']))} — {tx['comment']}"
        )
    return "\n".join(lines)
