from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_NAME = "Walro"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_TELEGRAM_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID", "").strip()
WALRO_TIMEZONE = os.getenv("WALRO_TIMEZONE", "Asia/Beirut").strip() or "Asia/Beirut"
DB_PATH = os.getenv("WALRO_DB_PATH", "data/walro.db").strip() or "data/walro.db"


def db_path() -> Path:
    return Path(DB_PATH)


def timezone() -> ZoneInfo:
    return ZoneInfo(WALRO_TIMEZONE)


def is_authorized(user_id: int | None) -> bool:
    """If ALLOWED_TELEGRAM_USER_ID is blank, allow anyone for easy local testing."""
    if user_id is None:
        return False
    if not ALLOWED_TELEGRAM_USER_ID:
        return True
    return str(user_id) == ALLOWED_TELEGRAM_USER_ID
