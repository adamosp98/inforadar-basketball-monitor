import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
SPORTS_TAG_ID = os.getenv("POLYMARKET_SPORTS_TAG_ID", "100639")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))
MARKET_REFRESH_SECONDS = int(os.getenv("MARKET_REFRESH_SECONDS", "300"))
PRICE_MOVE_PP = float(os.getenv("PRICE_MOVE_PP", "5"))
LINE_MOVE_MIN = float(os.getenv("LINE_MOVE_MIN", "1.0"))
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", "0"))
COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "900"))
MAX_EVENTS_PAGES = int(os.getenv("MAX_EVENTS_PAGES", "5"))
STATE_FILE = Path(os.getenv("STATE_FILE", "polymarket_state.json"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Polymarket's sports metadata uses league/sport codes. Keep this configurable so
# the monitor can be expanded as Polymarket adds basketball competitions.
DEFAULT_BASKETBALL_SPORTS = {
    "nba", "wnba", "ncaab", "ncaaw", "nbl", "b-league", "bleague",
    "euroleague", "acb", "liga-acb", "vtb", "aba", "lkl", "betclic",
    "bundesliga", "basketball-bundesliga", "greek-basketball",
    "turkish-basketball", "french-basketball", "italian-basketball",
    "spanish-basketball", "israeli-basketball", "australian-basketball",
}
BASKETBALL_SPORTS = {
    x.strip().lower() for x in os.getenv(
        "BASKETBALL_SPORTS",
        ",".join(sorted(DEFAULT_BASKETBALL_SPORTS)),
    ).split(",") if x.strip()
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "InfoRadar-Polymarket-Monitor/1.0"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"markets": {}, "alerts": {}, "last_refresh": 0}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"markets": {}, "alerts": {}, "last_refresh": 0}


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_FILE)


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    r = SESSION.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def extract_line(text: str) -> float | None:
    # Covers common sports-market phrasing such as -4.5, +4.5, 164.5.
    if not text:
        return None
    matches = re.findall(r"(?<!\d)([+-]?\d+(?:\.\d+)?)(?!\d)", text)
    if not matches:
        return None
    # Prefer a decimal number because spread/total lines normally contain .5.
    for raw in matches:
        if "." in raw:
            try:
                return float(raw)
            except ValueError:
                pass
    try:
        return float(matches[-1])
    except ValueError:
        return None


def classify_market(market: dict[str, Any]) -> str | None:
    sports = market.get("sports") or {}
    mtype = sports.get("sportsMarketType") or sports.get("sports_market_type")
    if mtype in ("spreads", "spread"):
        return "spread"
    if mtype in ("totals", "total"):
        return "total"

    text = " ".join(str(market.get(k, "")) for k in ("question", "slug", "groupItemTitle")).lower()
    if "spread" in text or "handicap" in text:
        return "spread"
    if "over/under" in text or "total" in text:
        return "total"
    return None


def is_basketball(market: dict[str, Any]) -> bool:
    sports = market.get("sports") or {}
    sport = str(sports.get("sport") or "").lower()
    league = str(sports.get("league") or "").lower()
    text = " ".join(
        str(market.get(k, "")) for k in ("question", "slug", "groupItemTitle", "category")
    ).lower()

    if sport in BASKETBALL_SPORTS or league in BASKETBALL_SPORTS:
        return True

    # Conservative fallbacks for common basketball identifiers.
    keywords = ("nba", "wnba", "ncaab", "ncaaw", "euroleague", "acb", "b-league", "basketball")
    return any(k in sport or k in league or k in text for k in keywords)


def discover_markets() -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    after = None

    for _ in range(MAX_EVENTS_PAGES):
        params: dict[str, Any] = {
            "tag_id": SPORTS_TAG_ID,
            "active": "true",
            "closed": "false",
            "limit": 100,
            "order": "startTime",
            "ascending": "true",
        }
        if after:
            params["after_cursor"] = after

        data = get_json(f"{GAMMA}/events/keyset", params)
        events = data.get("events", []) if isinstance(data, dict) else []
        after = data.get("next_cursor") if isinstance(data, dict) else None
        if not events:
            break

        for event in events:
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                if not is_basketball(market):
                    continue
                mtype = classify_market(market)
                if mtype not in ("spread", "total"):
                    continue
                liquidity = float(market.get("liquidity") or 0)
                if liquidity < MIN_LIQUIDITY:
                    continue
                token_ids = parse_jsonish(market.get("clobTokenIds"))
                if not isinstance(token_ids, list) or not token_ids:
                    continue
                market_id = str(market.get("id"))
                sports = market.get("sports") or {}
                markets.append({
                    "market_id": market_id,
                    "event_id": str(event.get("id") or ""),
                    "game_id": str(sports.get("gameId") or sports.get("game_id") or event.get("id") or ""),
                    "event_title": event.get("title") or market.get("groupItemTitle") or market.get("question") or market_id,
                    "question": market.get("question") or "",
                    "slug": market.get("slug") or "",
                    "market_type": mtype,
                    "line": extract_line(str(market.get("question") or market.get("slug") or "")),
                    "token_ids": [str(x) for x in token_ids],
                    "liquidity": liquidity,
                    "url": f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else "https://polymarket.com/",
                })

        if not after:
            break

    # One market per ID, deterministic order.
    unique = {m["market_id"]: m for m in markets}
    return list(unique.values())


def get_midpoints(token_ids: list[str]) -> dict[str, float]:
    if not token_ids:
        return {}
    payload = [{"token_id": token_id} for token_id in token_ids]
    try:
        r = SESSION.post(f"{CLOB}/midpoints", json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        out: dict[str, float] = {}
        if isinstance(data, dict):
            for token_id, body in data.items():
                raw = body.get("mid") if isinstance(body, dict) else body
                try:
                    out[str(token_id)] = float(raw)
                except (TypeError, ValueError):
                    pass
        return out
    except Exception:
        out = {}
        for token_id in token_ids:
            try:
                data = get_json(f"{CLOB}/midpoint", {"token_id": token_id})
                out[token_id] = float(data.get("mid"))
            except Exception:
                continue
        return out


def alert_allowed(state: dict[str, Any], dedupe: str) -> bool:
    last = float(state.get("alerts", {}).get(dedupe, 0) or 0)
    return time.time() - last >= COOLDOWN_SECONDS


def mark_alert(state: dict[str, Any], dedupe: str) -> None:
    state.setdefault("alerts", {})[dedupe] = time.time()


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM NOT CONFIGURED]\n" + message)
        return
    r = SESSION.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()


def market_label(m: dict[str, Any]) -> str:
    line = m.get("line")
    suffix = f" {line:g}" if isinstance(line, (int, float)) else ""
    return f"{m['event_title']} • {m['market_type'].upper()}{suffix}"


def compare_market(state: dict[str, Any], m: dict[str, Any], prices: dict[str, float]) -> None:
    key = m["market_id"]
    prev = state.setdefault("markets", {}).get(key)
    now = utc_now()

    current_price = None
    if m["token_ids"]:
        current_price = prices.get(m["token_ids"][0])

    snapshot = {
        "event_title": m["event_title"],
        "event_id": m["event_id"],
        "game_id": m["game_id"],
        "market_type": m["market_type"],
        "line": m.get("line"),
        "price": current_price,
        "question": m["question"],
        "url": m["url"],
        "seen_at": now,
    }

    if prev:
        prev_line = prev.get("line")
        new_line = m.get("line")
        if prev_line is not None and new_line is not None and prev_line != new_line:
            move = new_line - prev_line
            if abs(move) >= LINE_MOVE_MIN:
                dedupe = f"line:{m['game_id']}:{m['market_type']}:{prev_line}:{new_line}"
                if alert_allowed(state, dedupe):
                    message = (
                        f"🏀 POLYMARKET LINE MOVE\n\n"
                        f"{m['event_title']}\n"
                        f"Market: {m['market_type'].upper()}\n"
                        f"Line: {prev_line:g} → {new_line:g} ({move:+g})\n\n"
                        f"{m['url']}"
                    )
                    print(message)
                    send_telegram(message)
                    mark_alert(state, dedupe)

        prev_price = prev.get("price")
        if prev_price is not None and current_price is not None:
            change_pp = (current_price - prev_price) * 100
            if abs(change_pp) >= PRICE_MOVE_PP:
                dedupe = f"price:{key}:{round(prev_price,4)}:{round(current_price,4)}"
                if alert_allowed(state, dedupe):
                    message = (
                        f"📈 POLYMARKET PRICE MOVE\n\n"
                        f"{m['event_title']}\n"
                        f"Market: {m['market_type'].upper()}"
                        f"{f' {m["line"]:g}' if isinstance(m.get('line'), (int, float)) else ''}\n"
                        f"Price: {prev_price:.3f} → {current_price:.3f} ({change_pp:+.1f}pp)\n\n"
                        f"{m['url']}"
                    )
                    print(message)
                    send_telegram(message)
                    mark_alert(state, dedupe)

    state["markets"][key] = snapshot


def main() -> None:
    state = load_state()
    markets: list[dict[str, Any]] = []
    last_refresh = 0.0

    while True:
        try:
            now = time.time()
            if not markets or now - last_refresh >= MARKET_REFRESH_SECONDS:
                markets = discover_markets()
                last_refresh = now
                print(f"Discovered {len(markets)} active basketball spread/total markets.")

            token_ids = [token for m in markets for token in m["token_ids"]]
            # Deduplicate to avoid redundant public requests.
            token_ids = list(dict.fromkeys(token_ids))
            prices = get_midpoints(token_ids)
            for m in markets:
                compare_market(state, m, prices)
            state["last_refresh"] = last_refresh
            save_state(state)

            print(f"Checked {len(markets)} markets at {utc_now()}; next poll in {POLL_SECONDS}s")
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            save_state(state)
            raise
        except Exception as exc:
            print(f"Loop error: {exc}")
            time.sleep(min(POLL_SECONDS, 30))


if __name__ == "__main__":
    main()
