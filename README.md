# InfoRadar Basketball Movement Monitor

Monitors a public InfoRadar.live basketball game page with Playwright, reads the visible market table, compares the newest row with the previous snapshot, and sends Telegram alerts for significant handicap, total, or price movements.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
python monitor.py
```

Put one or more public game URLs in `GAME_URLS`.

The default example is:
`https://inforadar.live/#/dashboard/basketball/game/12054577`

Create a Telegram bot with BotFather, start a chat with it, then fill `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Important: check InfoRadar.live terms before automated monitoring at scale. This tool does not bypass login, CAPTCHA, or anti-bot controls.
