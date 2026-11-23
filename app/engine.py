"""Core engine: zone pre-calculation, live touch scanning, test scan."""
import threading
import time
from datetime import datetime, time as dtime, timedelta

import pandas as pd
import pytz
from logzero import logger

from . import config, db, feeds, notifier
from .angel import AngelClient
from .universe import load_universe
from .zones import detect_zones, in_zone, is_hit

IST = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def trading_day(now: datetime = None) -> str:
    """9:15 AM today to 9:14 AM tomorrow counts as the same trading session."""
    now = now or now_ist()
    if now.time() < dtime(9, 15):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def market_open(now: datetime = None) -> bool:
    now = now or now_ist()
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)


class Engine:
    def __init__(self):
        self.angel = AngelClient()
        self.universe = []
        self.zone_cache = {}
        self.quotes = {}
        self.last_scan = None
        self.source = "-"
        self.ready = False
        self.refreshing = False
        self.progress = (0, 0)
        self._flag = threading.Lock()
        self._last_login_try = 0.0

    # ---------- lifecycle ----------
    def startup(self):
        try:
            self.reload_universe()
            self.login()
            self.load_zone_cache()
            today = now_ist().strftime("%Y-%m-%d")
            updated = (db.get_meta("zones_updated") or "")[:10]
            if not self.zone_cache or updated != today:
                self.refresh_zones_async()
        except Exception:
            logger.exception("startup failed")
        finally:
            self.ready = True

    def reload_universe(self):
        self.universe = load_universe()
        logger.info("Universe size: %d", len(self.universe))

    def login(self) -> bool:
        self._last_login_try = time.time()
        return self.angel.login()

    # ---------- stage 1: zone pre-calculation ----------
    def load_zone_cache(self):
        cache = {}
        with db.conn() as c:
            for r in c.execute("SELECT * FROM zones"):
                cache.setdefault(r["symbol"], []).append(dict(r))
        self.zone_cache = cache

    def refresh_zones_async(self) -> bool:
        if self.refreshing:
            return False
        threading.Thread(target=self.refresh_zones, daemon=True).start()
        return True

    def refresh_zones(self) -> bool:
        with self._flag:
            if self.refreshing:
                return False
            self.refreshing = True
        try:
            if not self.universe:
                self.reload_universe()
            stocks = self.universe
            total = len(stocks)
            self.progress = (0, total)
            today = now_ist().strftime("%Y-%m-%d")
            candles = {}

            if self.angel.connected:
                for idx, s in enumerate(stocks):
                    rows = self.angel.daily_candles(s["token"]) if s.get("token") else None
                    if rows:
                        candles[s["symbol"]] = rows
                    self.progress = (idx + 1, total)
                    time.sleep(0.4)

            missing = [s for s in stocks if s["symbol"] not in candles]
            if missing:
                logger.info("Fetching %d stocks via yfinance fallback", len(missing))
                candles.update(feeds.yf_history(missing))
            self.progress = (total, total)

            n_zones = 0
            with db.conn() as c:
                for sym, rows in candles.items():
                    if len(rows) < 30:
                        continue
                    c.execute("DELETE FROM candles WHERE symbol=?", (sym,))
                    c.executemany(
                        "INSERT OR REPLACE INTO candles(symbol,d,o,h,l,c) VALUES (?,?,?,?,?,?)",
                        [(sym,) + tuple(r) for r in rows],
                    )
                    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
                    df = df[df["date"] < today]
                    zones = detect_zones(df)
                    c.execute("DELETE FROM zones WHERE symbol=?", (sym,))
                    c.executemany(
                        "INSERT INTO zones(symbol,side,pattern,proximal,distal,freshness,touches,formed)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        [
                            (sym, z["side"], z["pattern"], z["proximal"], z["distal"],
                             z["freshness"], z["touches"], z["formed"])
                            for z in zones
                        ],
                    )
                    n_zones += len(zones)
            db.set_meta("zones_updated", now_ist().strftime("%Y-%m-%d %H:%M:%S"))
            self.load_zone_cache()
            logger.info("Zones refreshed: %d zones across %d stocks", n_zones, len(candles))
            return True
        except Exception:
            logger.exception("refresh_zones failed")
            return False
        finally:
            self.refreshing = False

    # ---------- stage 2: live touch detection ----------
    def _fetch_quotes(self) -> dict:
        stocks = self.universe
        if self.angel.connected:
            tok2sym = {s["token"]: s["symbol"] for s in stocks if s.get("token")}
            raw = self.angel.quotes(list(tok2sym))
            out = {tok2sym[t]: q for t, q in raw.items() if t in tok2sym}
            if out:
                self.source = "Angel One"
                return out
            logger.warning("Angel One quotes empty; using yfinance for this cycle")
        self.source = "yfinance"
        return feeds.yf_quotes(stocks)

    def scan_live(self):
        if not self.ready or not market_open():
            return
        if not self.universe or not self.zone_cache:
            return
        if (
            not self.angel.connected
            and config.angel_configured()
            and time.time() - self._last_login_try > 120
        ):
            self.login()
        try:
            quotes = self._fetch_quotes()
        except Exception:
            logger.exception("quote fetch failed")
            return
        if not quotes:
            return
        self.quotes = quotes
        self.last_scan = now_ist()
        self._evaluate(quotes)

    def _evaluate(self, quotes: dict):
        now = now_ist()
        day = trading_day(now)
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        new_hits = []
        with db.conn() as c:
            for sym, q in quotes.items():
                ltp = q.get("ltp") or 0
                if ltp <= 0:
                    continue
                high = q.get("high") or ltp
                low = q.get("low") or ltp
                for z in self.zone_cache.get(sym, []):
                    if not is_hit(z, ltp, high, low):
                        continue
                    key = f"{z['side']}:{z['proximal']}:{z['distal']}"
                    cur = c.execute(
                        "INSERT OR IGNORE INTO touches(day,symbol,zone_key,side,pattern,proximal,"
                        "distal,freshness,first_ts) VALUES (?,?,?,?,?,?,?,?,?)",
                        (day, sym, key, z["side"], z["pattern"], z["proximal"],
                         z["distal"], z["freshness"], ts),
                    )
                    if cur.rowcount == 1:
                        new_hits.append(
                            {"symbol": sym, "side": z["side"], "pattern": z["pattern"],
                             "proximal": z["proximal"], "distal": z["distal"],
                             "freshness": z["freshness"], "ltp": ltp, "high": high,
                             "low": low, "time": now.strftime("%H:%M:%S")}
                        )
        for hit in new_hits:
            logger.info("TOUCH %s %s %s", hit["symbol"], hit["side"], hit["pattern"])
            notifier.alert_touch(hit)

    # ---------- views ----------
    def live_touches(self) -> list:
        day = trading_day()
        with db.conn() as c:
            rows = c.execute(
                "SELECT * FROM touches WHERE day=? ORDER BY first_ts DESC", (day,)
            ).fetchall()
        out = []
        for r in rows:
            q = self.quotes.get(r["symbol"], {})
            z = {"side": r["side"], "proximal": r["proximal"], "distal": r["distal"]}
            out.append(
                {
                    "id": f"{r['day']}|{r['symbol']}|{r['zone_key']}",
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "pattern": r["pattern"],
                    "proximal": r["proximal"],
                    "distal": r["distal"],
                    "freshness": r["freshness"],
                    "ltp": q.get("ltp"),
                    "high": q.get("high"),
                    "low": q.get("low"),
                    "time": r["first_ts"][11:19],
                    "in_zone": in_zone(z, q.get("ltp")),
                }
            )
        return out

    def test_scan(self):
        """After-market test: latest stored daily candle acts as 'today'."""
        with db.conn() as c:
            rows = [tuple(r) for r in c.execute(
                "SELECT symbol,d,o,h,l,c FROM candles ORDER BY symbol,d")]
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close"])
        out = []
        for sym, g in df.groupby("symbol"):
            g = g.reset_index(drop=True)
            if len(g) < 31:
                continue
            last = g.iloc[-1]
            ltp, high, low = float(last["close"]), float(last["high"]), float(last["low"])
            for z in detect_zones(g.iloc[:-1]):
                if is_hit(z, ltp, high, low):
                    out.append(
                        {
"id": f"test|{sym}|{z['side']}:{z['proximal']}:{z['distal']}",
"symbol": sym, "side": z["side"], "pattern": z["pattern"],
"proximal": z["proximal"], "distal": z["distal"],
"freshness": z["freshness"], "ltp": ltp, "high": high,
"low": low, "time": str(last["date"]),
"in_zone": in_zone(z, ltp),
}
)
out.sort(key=lambda t: (t["side"], t["symbol"]))
return out
def chart_data(self, symbol: str, live: bool) -> list:
        with db.conn() as c:
            rows = c.execute("SELECT d,o,h,l,c FROM candles WHERE symbol=? ORDER BY d", (symbol,)).fetchall()
        candles = [{"time": r["d"], "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"]} for r in rows]
        q = self.quotes.get(symbol)
        if live and q and market_open() and q.get("ltp"):
            today = now_ist().strftime("%Y-%m-%d")
            bar = {"time": today, "open": q.get("open") or q["ltp"], "high": q.get("high") or q["ltp"], "low": q.get("low") or q["ltp"], "close": q["ltp"]}
            if candles and candles[-1]["time"] == today:
                candles[-1] = bar
            else:
                candles.append(bar)
        return candles

    def status(self) -> dict:
        now = now_ist()
        zones = [z for lst in self.zone_cache.values() for z in lst]
        return {
            "angel": "Connected" if self.angel.connected else "Fallback",
            "angel_error": self.angel.error,
            "market": "LIVE" if market_open(now) else "CLOSED",
            "last_scan": self.last_scan.strftime("%H:%M:%S") if self.last_scan else "--:--:--",
            "source": self.source,
            "zones_total": len(zones),
            "demand": sum(1 for z in zones if z["side"] == "DEMAND"),
            "supply": sum(1 for z in zones if z["side"] == "SUPPLY"),
            "zones_updated": db.get_meta("zones_updated"),
            "refreshing": self.refreshing,
            "progress": f"{self.progress[0]}/{self.progress[1]}",
            "ready": self.ready,
            "server_time": now.strftime("%H:%M:%S"),
        }


engine = Engine()
