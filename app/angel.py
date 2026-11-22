"""Angel One SmartAPI wrapper: auto TOTP login, candles, bulk market data."""
import threading
import time
from datetime import datetime, timedelta

import pyotp
import pytz
from logzero import logger

from . import config

try:
    from SmartApi import SmartConnect
except Exception as _e:  # package missing -> Fallback Mode only
    SmartConnect = None
    logger.warning("SmartApi import failed: %s", _e)

IST = pytz.timezone("Asia/Kolkata")
AUTH_CODES = {"AG8001", "AG8002", "AG8003", "AB8051"}


class AngelClient:
    def __init__(self):
        self.smart = None
        self.jwt = None
        self.feed_token = None
        self.refresh_token = None
        self.connected = False
        self.error = ""
        self.lock = threading.RLock()

    # ---------- login ----------
    def login(self) -> bool:
        if SmartConnect is None:
            self.connected, self.error = False, "smartapi-python not installed"
            return False
        if not config.angel_configured():
            self.connected, self.error = False, "Angel One credentials not set"
            return False
        last_err = ""
        for attempt in range(2):
            try:
                smart = SmartConnect(api_key=config.ANGEL_API_KEY)
                totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
                data = smart.generateSession(
                    config.ANGEL_CLIENT_CODE, config.ANGEL_PIN, totp
                )
                if not data or not data.get("status"):
                    raise RuntimeError((data or {}).get("message", "login failed"))
                self.jwt = data["data"]["jwtToken"]
                self.refresh_token = data["data"].get("refreshToken")
                try:
                    self.feed_token = smart.getfeedToken()
                except Exception:
                    self.feed_token = data["data"].get("feedToken")
                with self.lock:
                    self.smart = smart
                self.connected, self.error = True, ""
                logger.info("Angel One login OK (jwt + feed token refreshed)")
                return True
            except Exception as e:
                last_err = str(e)
                logger.warning("Angel One login attempt %d failed: %s", attempt + 1, e)
                time.sleep(2)
        self.connected, self.error = False, last_err or "login failed"
        return False

    # ---------- generic call with retry / re-login ----------
    def _call(self, fn, tries: int = 3):
        for attempt in range(tries):
            try:
                with self.lock:
                    res = fn()
                if isinstance(res, dict) and res.get("status") is False:
                    code = str(res.get("errorcode") or res.get("errorCode") or "")
                    msg = str(res.get("message") or "").lower()
                    if code in AUTH_CODES or "invalid token" in msg or "token expired" in msg:
                        if attempt == 0 and self.login():
                            continue
                        return res
                    if "rate" in msg or "access denied" in msg:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                return res
            except Exception as e:
                logger.warning("SmartAPI call error (try %d): %s", attempt + 1, e)
                time.sleep(1.5 * (attempt + 1))
        return None

    # ---------- history ----------
    def daily_candles(self, token: str):
        """Last 365 days of ONE_DAY candles -> [(date, o, h, l, c)] or None."""
        if not self.connected:
            return None
        now = datetime.now(IST)
        params = {
            "exchange": "NSE",
            "symboltoken": str(token),
            "interval": "ONE_DAY",
            "fromdate": (now - timedelta(days=365)).strftime("%Y-%m-%d 09:15"),
            "todate": now.strftime("%Y-%m-%d %H:%M"),
        }
        res = self._call(lambda: self.smart.getCandleData(params))
        if not res or not res.get("status") or not res.get("data"):
            return None
        rows = []
        for r in res["data"]:
            try:
                rows.append(
                    (str(r[0])[:10], float(r[1]), float(r[2]), float(r[3]), float(r[4]))
                )
            except Exception:
                continue
        return rows or None

    # ---------- live bulk quotes ----------
    def quotes(self, tokens: list) -> dict:
        """getMarketData(OHLC) in batches of 50 -> {token: {ltp, open, high, low}}."""
        out = {}
        if not self.connected or not tokens:
            return out
        batches = [tokens[i : i + 50] for i in range(0, len(tokens), 50)]
        for bi, batch in enumerate(batches):
            res = self._call(
                lambda b=batch: self.smart.getMarketData("OHLC", {"NSE": b})
            )
            if res and res.get("status") and res.get("data"):
                for q in res["data"].get("fetched", []):
                    try:
                        out[str(q["symbolToken"])] = {
                            "ltp": float(q.get("ltp") or 0),
                            "open": float(q.get("open") or 0),
                            "high": float(q.get("high") or 0),
                            "low": float(q.get("low") or 0),
                        }
                    except Exception:
                        continue
            else:
                logger.warning("getMarketData batch %d failed: %s", bi, res)
            if bi < len(batches) - 1:
                time.sleep(1.1)  # SmartAPI quote limit ~1 req/sec
        return out
