# InfoRadar-style Polymarket Basketball Monitor

This version replaces the InfoRadar browser scraper with Polymarket's public market-data APIs.

It discovers active sports markets tagged as games, filters for basketball competitions, watches spread and total markets, records the previous snapshot locally, and sends Telegram alerts when:

- a new spread/total line differs from the previous line for the same game/market,
- the first outcome price changes by at least `PRICE_MOVE_PP` percentage points.

Polymarket's market-discovery documentation states that market discovery data is public and does not require authentication. Sports metadata exposes `sportsMarketType` values such as `moneyline`, `spreads`, and `totals`. The public CLOB midpoint endpoints provide current prices for market tokens. See the official docs cited in the project notes below.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python test_logic.py
python polymarket_monitor.py
```

Add the Telegram bot token and chat ID to `.env` before expecting external alerts.

## What it does not do

This project does not place trades. It only reads public market data and sends notifications.

Polymarket creates separate sports markets/lines, so a handicap move is detected by seeing a different spread market line for the same game rather than assuming that one market's line mutates in place.

## Thresholds

- `PRICE_MOVE_PP=5` means a price change of 5 percentage points, e.g. `0.55 -> 0.60`.
- `LINE_MOVE_MIN=1.0` means a one-point or larger spread/total line change.
- `MARKET_REFRESH_SECONDS=300` refreshes the market universe every 5 minutes.
- `POLL_SECONDS=15` checks current prices every 15 seconds.

The monitor uses public endpoints, but availability and rate limits can change; keep the polling interval reasonable.
