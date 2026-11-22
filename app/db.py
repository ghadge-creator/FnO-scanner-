import contextlib
import sqlite3
import threading
from typing import Optional

from .config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS candles(
    symbol TEXT NOT NULL, d TEXT NOT NULL,
    o REAL, h REAL, l REAL, c REAL,
    PRIMARY KEY(symbol, d)
);
CREATE TABLE IF NOT EXISTS zones(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, side TEXT NOT NULL, pattern TEXT NOT NULL,
    proximal REAL NOT NULL, distal REAL NOT NULL,
    freshness TEXT NOT NULL, touches INTEGER NOT NULL, formed TEXT
);
CREATE INDEX IF NOT EXISTS idx_zones_symbol ON zones(symbol);
CREATE TABLE IF NOT EXISTS touches(
    day TEXT NOT NULL, symbol TEXT NOT NULL, zone_key TEXT NOT NULL,
    side TEXT, pattern TEXT, proximal REAL, distal REAL,
    freshness TEXT, first_ts TEXT,
    PRIMARY KEY(day, symbol, zone_key)
);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


@contextlib.contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(str(DB_PATH), timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def get_meta(key: str) -> Optional[str]:
    with conn() as c:
        row = c.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row["v"] if row else None


def set_meta(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)", (key, value))
