from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import db_path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL CHECK (mode IN ('fixed', 'monthly')),
    total_budget_usd REAL NOT NULL CHECK (total_budget_usd > 0),
    daily_allowance_usd REAL NOT NULL CHECK (daily_allowance_usd > 0),
    starting_surplus_usd REAL NOT NULL DEFAULT 0,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_id INTEGER NOT NULL REFERENCES budgets(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    tx_date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'surplus_expense', 'income')),
    amount_usd REAL NOT NULL CHECK (amount_usd > 0),
    original_amount REAL NOT NULL CHECK (original_amount > 0),
    currency TEXT NOT NULL,
    category_code TEXT,
    comment TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_budget_date
ON transactions (budget_id, tx_date);

CREATE INDEX IF NOT EXISTS idx_transactions_budget_created
ON transactions (budget_id, created_at, id);
"""

DEFAULT_CATEGORIES = {
    "f": "food",
    "t": "transport",
    "s": "shopping",
}

DEFAULT_SETTINGS = {
    "fx_usd": "1",
    # AED is commonly fixed near this level. You can still override it with /setrate aed 3.67.
    "fx_aed": "3.6725",
}


def get_conn() -> sqlite3.Connection:
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for code, name in DEFAULT_CATEGORIES.items():
            conn.execute(
                "INSERT OR IGNORE INTO categories (code, name, active) VALUES (?, ?, 1)",
                (code, name),
            )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
