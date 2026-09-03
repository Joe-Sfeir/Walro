from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from . import core
from .config import BOT_NAME, TELEGRAM_BOT_TOKEN, is_authorized
from .db import get_conn, init_db
from .messages import format_history, format_summary, format_transaction_reply, start_help
from .parser import ParseError, parse_transaction
from .utils import money, signed_money, today_local

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


async def guard(update: Update) -> bool:
    user = update.effective_user
    if is_authorized(user.id if user else None):
        return True
    if update.message:
        await update.message.reply_text(
            f"{BOT_NAME} is private. Your Telegram user ID is {user.id if user else 'unknown'}."
        )
    return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    await update.message.reply_text(start_help())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    await update.message.reply_text(start_help())


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Your Telegram user ID is: {user.id if user else 'unknown'}")


def _parse_amount_currency_days(args: list[str]) -> tuple[float, str, int]:
    # Supports:
    # /startbudget 3000 25
    # /startbudget 3000 usd 25
    # /startbudget 3000 aed 25
    if len(args) == 2:
        amount = float(args[0])
        currency = "usd"
        days = int(args[1])
    elif len(args) == 3:
        amount = float(args[0])
        currency = args[1].lower()
        days = int(args[2])
    else:
        raise core.WalroError("Use /startbudget 3000 25 or /startbudget 3000 aed 25")
    return amount, currency, days


async def cmd_startbudget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        amount, currency, days = _parse_amount_currency_days(context.args)
        with get_conn() as conn:
            total_usd = core.to_usd(conn, amount, currency)
            budget = core.start_fixed_budget(conn, total_usd, days)
            conn.commit()
            await update.message.reply_text(
                "Started fixed budget.\n"
                f"Total: {money(total_usd)}\n"
                f"Days: {days}\n"
                f"Daily allowance: {money(float(budget['daily_allowance_usd']))}\n"
                f"Period: {budget['start_date']} → {budget['end_date']}"
            )
    except Exception as e:
        await update.message.reply_text(f"Could not start budget: {e}")


async def cmd_startmonth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        if len(context.args) == 1:
            amount = float(context.args[0])
            currency = "usd"
        elif len(context.args) == 2:
            amount = float(context.args[0])
            currency = context.args[1].lower()
        else:
            raise core.WalroError("Use /startmonth 3000 or /startmonth 3000 aed")

        with get_conn() as conn:
            total_usd = core.to_usd(conn, amount, currency)
            budget = core.start_monthly_budget(conn, total_usd)
            conn.commit()
            days = core.inclusive_days(core.parse_date(budget["start_date"]), core.parse_date(budget["end_date"]))
            await update.message.reply_text(
                "Started monthly budget.\n"
                f"Total: {money(total_usd)}\n"
                f"Days in this cycle: {days}\n"
                f"Daily allowance: {money(float(budget['daily_allowance_usd']))}\n"
                f"Period: {budget['start_date']} → {budget['end_date']}"
            )
    except Exception as e:
        await update.message.reply_text(f"Could not start monthly budget: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        with get_conn() as conn:
            budget = core.require_active_budget(conn)
            conn.commit()
            summary = core.calculate_summary(conn, budget)
            breakdown = core.category_breakdown_today(conn, budget["id"])
            await update.message.reply_text(format_summary(summary, breakdown))
    except Exception as e:
        await update.message.reply_text(f"Could not get status: {e}")


async def cmd_setrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        if len(context.args) != 2:
            raise core.WalroError("Use /setrate aed 3.67 or /setrate lbp 89500")
        currency = context.args[0].lower()
        rate = float(context.args[1])
        with get_conn() as conn:
            core.set_fx_rate(conn, currency, rate)
            conn.commit()
        await update.message.reply_text(
            f"Set {currency.upper()} rate to {rate:g} {currency.upper()} per 1 USD."
        )
    except Exception as e:
        await update.message.reply_text(f"Could not set rate: {e}")


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    with get_conn() as conn:
        lines = ["FX rates, currency units per 1 USD:", "USD: 1"]
        for c in ["aed", "lbp"]:
            raw = core.get_setting(conn, f"fx_{c}")
            lines.append(f"{c.upper()}: {raw if raw else 'not set'}")
    await update.message.reply_text("\n".join(lines))


async def cmd_addcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        if len(context.args) < 2:
            raise core.WalroError("Use /addcategory e entertainment")
        code = context.args[0]
        name = " ".join(context.args[1:])
        with get_conn() as conn:
            core.add_category(conn, code, name)
            conn.commit()
        await update.message.reply_text(f"Added category {code.lower()} = {name.lower()}.")
    except Exception as e:
        await update.message.reply_text(f"Could not add category: {e}")


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    with get_conn() as conn:
        rows = core.list_categories(conn)
    lines = ["Categories:"] + [f"{r['code']} = {r['name']}" for r in rows]
    await update.message.reply_text("\n".join(lines))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        limit = int(context.args[0]) if context.args else 10
        with get_conn() as conn:
            rows = core.get_history(conn, limit)
        await update.message.reply_text(format_history(rows))
    except Exception as e:
        await update.message.reply_text(f"Could not get history: {e}")


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        with get_conn() as conn:
            tx = core.undo_last(conn)
            budget = core.require_active_budget(conn)
            summary = core.calculate_summary(conn, budget)
            conn.commit()
        await update.message.reply_text(
            f"Undid #{tx['id']}: {tx['comment']} ({money(float(tx['amount_usd']))}).\n"
            f"Today remaining: {signed_money(float(summary['today_remaining_usd']))}\n"
            f"Surplus: {signed_money(float(summary['surplus_usd']))}"
        )
    except Exception as e:
        await update.message.reply_text(f"Could not undo: {e}")


async def cmd_resetbudget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        with get_conn() as conn:
            core.deactivate_active_budgets(conn)
            conn.commit()
        await update.message.reply_text("Active budget reset. Start a new one with /startbudget or /startmonth.")
    except Exception as e:
        await update.message.reply_text(f"Could not reset budget: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    text = update.message.text or ""
    try:
        parsed = parse_transaction(text)
        with get_conn() as conn:
            tx, _budget, summary = core.log_transaction(conn, parsed)
            conn.commit()
        await update.message.reply_text(format_transaction_reply(tx, summary))
    except (ParseError, core.WalroError) as e:
        await update.message.reply_text(str(e))
    except Exception as e:
        logger.exception("Unexpected error while handling text")
        await update.message.reply_text(f"Unexpected error: {e}")


def build_application():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("startbudget", cmd_startbudget))
    app.add_handler(CommandHandler("startmonth", cmd_startmonth))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("setrate", cmd_setrate))
    app.add_handler(CommandHandler("rates", cmd_rates))
    app.add_handler(CommandHandler("addcategory", cmd_addcategory))
    app.add_handler(CommandHandler("categories", cmd_categories))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("resetbudget", cmd_resetbudget))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main() -> None:
    init_db()
    app = build_application()
    logger.info("Walro is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
