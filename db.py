import sqlite3
from pathlib import Path

DB_PATH = Path('state.db')

def connect():
    con = sqlite3.connect(DB_PATH)
    con.execute('CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, game_url TEXT, game_name TEXT, market TEXT, selection TEXT, line REAL, price REAL, seen_at TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS alerts (dedupe_key TEXT PRIMARY KEY, sent_at REAL)')
    con.commit()
    return con

def get_snapshot(con, key):
    row = con.execute('SELECT game_url, game_name, market, selection, line, price, seen_at FROM snapshots WHERE key=?', (key,)).fetchone()
    if not row:
        return None
    return {'game_url': row[0], 'game_name': row[1], 'market': row[2], 'selection': row[3], 'line': row[4], 'price': row[5], 'seen_at': row[6]}

def upsert_snapshot(con, key, item):
    con.execute('''INSERT INTO snapshots(key, game_url, game_name, market, selection, line, price, seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET game_url=excluded.game_url, game_name=excluded.game_name,
                   market=excluded.market, selection=excluded.selection, line=excluded.line,
                   price=excluded.price, seen_at=excluded.seen_at''',
                (key, item['game_url'], item['game_name'], item['market'], item['selection'], item.get('line'), item.get('price'), item['seen_at']))
    con.commit()

def alert_recent(con, key, now_ts, cooldown):
    row = con.execute('SELECT sent_at FROM alerts WHERE dedupe_key=?', (key,)).fetchone()
    return bool(row and now_ts - row[0] < cooldown)

def mark_alert(con, key, now_ts):
    con.execute('INSERT INTO alerts(dedupe_key, sent_at) VALUES (?, ?) ON CONFLICT(dedupe_key) DO UPDATE SET sent_at=excluded.sent_at', (key, now_ts))
    con.commit()
