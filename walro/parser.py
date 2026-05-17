from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED_CURRENCIES = {"usd", "aed", "lbp"}

EXPENSE_RE = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<currency>usd|aed|lbp)\s+"
    r"(?P<category>[A-Za-z][A-Za-z0-9_-]*)\s+"
    r"(?P<comment>.+)$",
    re.IGNORECASE,
)

SURPLUS_EXPENSE_RE = re.compile(
    r"^S\s+"
    r"(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<currency>usd|aed|lbp)\s+"
    r"(?P<category>[A-Za-z][A-Za-z0-9_-]*)\s+"
    r"(?P<comment>.+)$",
    re.IGNORECASE,
)

INCOME_RE = re.compile(
    r"^\+\s*"
    r"(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<currency>usd|aed|lbp)\s+"
    r"(?P<comment>.+)$",
    re.IGNORECASE,
)


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTransaction:
    type: str
    amount: float
    currency: str
    category_code: str | None
    comment: str


def _amount(raw: str) -> float:
    amount = float(raw)
    if amount <= 0:
        raise ParseError("Amount must be greater than 0.")
    return amount


def parse_transaction(text: str) -> ParsedTransaction:
    text = text.strip()

    m = INCOME_RE.match(text)
    if m:
        return ParsedTransaction(
            type="income",
            amount=_amount(m.group("amount")),
            currency=m.group("currency").lower(),
            category_code=None,
            comment=m.group("comment").strip(),
        )

    m = SURPLUS_EXPENSE_RE.match(text)
    if m:
        return ParsedTransaction(
            type="surplus_expense",
            amount=_amount(m.group("amount")),
            currency=m.group("currency").lower(),
            category_code=m.group("category").lower(),
            comment=m.group("comment").strip(),
        )

    m = EXPENSE_RE.match(text)
    if m:
        return ParsedTransaction(
            type="expense",
            amount=_amount(m.group("amount")),
            currency=m.group("currency").lower(),
            category_code=m.group("category").lower(),
            comment=m.group("comment").strip(),
        )

    raise ParseError(
        "Invalid format. Use one of these:\n"
        "22 aed f daves hot chicken\n"
        "S 200 usd s headphones\n"
        "+500 usd salary"
    )
