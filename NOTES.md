## Design notes and current public API assumptions

- Gamma market/event discovery is public and unauthenticated.
- Sports markets expose a `sports.sportsMarketType` field; documented values include `moneyline`, `spreads`, and `totals`.
- A sports game can have multiple events/markets, including separate lines, so the monitor treats a new spread/total line as a line-movement event.
- Public CLOB midpoint endpoints are used for current prices; no trading credentials are required.

Official documentation:
- https://docs.polymarket.com/market-data/discover-markets
- https://docs.polymarket.com/trading/quickstart
