# Walro

Walro is a private Telegram spending tracker with:

- USD as the base currency
- inputs in USD, AED, and LBP
- fixed daily allowance
- separate surplus/deficit pool
- strict spending format
- SQLite storage

## 1. Create the Telegram bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Copy the bot token.

## 2. Set up locally

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Mac/Linux:

```bash
source .venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Create your `.env`:

```bash
cp .env.example .env
```

On Windows PowerShell, if `cp` does not work:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ALLOWED_TELEGRAM_USER_ID=
WALRO_TIMEZONE=Asia/Beirut
WALRO_DB_PATH=data/walro.db
```

Run Walro:

```bash
python -m walro.bot
```

## 3. Lock the bot to only you

First run the bot with `ALLOWED_TELEGRAM_USER_ID` empty.

In Telegram, send:

```text
/whoami
```

Copy the number into `.env`:

```env
ALLOWED_TELEGRAM_USER_ID=123456789
```

Restart the bot.

## 4. Start a budget

Fixed duration:

```text
/startbudget 3000 25
```

This means 3000 USD over 25 calendar days.

You can also start with another currency:

```text
/startbudget 11000 aed 25
```

Monthly mode:

```text
/startmonth 3000
```

This starts today and runs until the end of the current month. On the next month, Walro creates the new monthly cycle and carries surplus/deficit forward.

## 5. Set exchange rates

Rates mean: currency units per 1 USD.

```text
/setrate aed 3.67
/setrate lbp 89500
```

Check rates:

```text
/rates
```

## 6. Log spending

Normal daily expense:

```text
22 aed f daves hot chicken
```

Format:

```text
amount currency category comment
```

Surplus expense:

```text
S 200 usd s headphones
```

Money added:

```text
+500 usd salary
```

## 7. Categories

Default categories:

```text
f = food
t = transport
s = shopping
```

Add a category:

```text
/addcategory e entertainment
```

List categories:

```text
/categories
```

## 8. Useful commands

```text
/status
/history
/history 20
/undo
/resetbudget
/help
```

## 9. How the budget logic works

Example:

- Budget: 3000 USD
- Days: 30
- Daily allowance: 100 USD

If today you spend 60 USD, the 40 USD does not immediately enter surplus. It enters surplus tomorrow, when today is closed.

If today you spend 120 USD, tomorrow your surplus decreases by 20 USD.

If Walro is offline for 5 days, it automatically counts those missed calendar days the next time you message it.

Surplus expenses using `S` do not affect today's daily allowance. They hit surplus directly.

Income using `+` goes directly into surplus.

## 10. Render note

This project includes `render.yaml` for a Render worker:

```bash
python -m walro.bot
```

For serious use, make sure your database persists. SQLite on an ephemeral free web service is not safe for long-term storage because it can be lost after restart, redeploy, or spin-down. A paid persistent disk or a real hosted database is safer.
