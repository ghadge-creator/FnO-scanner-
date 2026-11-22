import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import pyotp
import pytz

IST = pytz.timezone("Asia/Kolkata")

try:
    from SmartApi import SmartConnect
    HAS_SMARTAPI = True
    IMPORT_ERROR = ""
except Exception as e:
    SmartConnect = None
    HAS_SMARTAPI = False
    IMPORT_ERROR = str(e)


class AngelClient:
    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY", "").strip()
        self.client_code = os.getenv("ANGEL_CLIENT_CODE", "").strip()
        self.pin = os.getenv("ANGEL_PIN", "").strip()
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", "").strip()
        self.smart: Optional[SmartConnect] = None
        self.jwt_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.connected: bool = False
        self.status_msg: str = "Not initialized"
        self.last_login_date: Optional[str] = None
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.client_code and self.pin and self.totp_secret)

    def login(self, force: bool = False) -> bool:
        with self._lock:
            if not HAS_SMARTAPI:
                self.connected = False
                self.status_msg = f"smartapi-python import error: {IMPORT_ERROR}"
                return False

            if not self.is_configured():
                self.connected = False
                self.status_msg = "Angel One credentials missing in Env"
                return False

            today_str = datetime.now(IST).strftime("%Y-%m-%d")
            if self.connected and self.smart and self.last_login_date == today_str and not force:
                return True

            try:
                smart = SmartConnect(api_key=self.api_key)
                totp = pyotp.TOTP(self.totp_secret).now()
                data = smart.generateSession(self.client_code, self.pin, totp)
                if data and data.get("status"):
                    self.smart = smart
                    self.jwt_token = data["data"]["jwtToken"]
                    self.feed_token = smart.getfeedToken()
                    self.connected = True
                    self.last_login_date = today_str
                    self.status_msg = "Connected"
                    return True
                else:
                    self.connected = False
                    self.status_msg = f"Login failed: {data.get('message', 'Unknown error')}"
                    return False
            except Exception as e:
                self.connected = False
                self.status_msg = f"Login exception: {e}"
                return False

    def get_historical_candles(
        self,
        symbol_token: str,
        interval: str = "ONE_DAY",
        days: int = 220,
        exchange: str = "NFO",
    ) -> Optional[pd.DataFrame]:
        if not self.login():
            return None

        now_ist = datetime.now(IST)
        from_dt = now_ist - timedelta(days=days)
        params = {
            "exchange": exchange,
            "symboltoken": str(symbol_token),
            "interval": interval,
            "fromdate": from_dt.strftime("%Y-%m-%d 09:00"),
            "todate": now_ist.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            res = self.smart.getCandleData(params)
            if not res or not res.get("status") or not res.get("data"):
                return None
            rows = res["data"]
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.dropna(subset=["open", "high", "low", "close"], inplace=True)
            df.sort_values("timestamp", inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df
        except Exception:
            return None

    def get_ltp_batch(self, tokens: List[str], exchange: str = "NFO") -> Dict[str, float]:
        quotes = self.get_full_quotes(tokens, exchange=exchange)
        return {tok: q["ltp"] for tok, q in quotes.items() if q.get("ltp", 0) > 0}

    def get_full_quotes(self, tokens: List[str], exchange: str = "NFO") -> Dict[str, dict]:
        """
        Fetches FULL market data (LTP, Volume, Total Buy Qty, Total Sell Qty, High/Low/Open)
        in batches of 50 symbols per API call so rate limits are never hit.
        """
        out: Dict[str, dict] = {}
        if not tokens or not self.login():
            return out

        clean_tokens = [str(t) for t in tokens if t]
        chunk_size = 50
        for i in range(0, len(clean_tokens), chunk_size):
            batch = clean_tokens[i : i + chunk_size]
            try:
                res = self.smart.getMarketData("FULL", {exchange: batch})
                if res and res.get("status") and res.get("data"):
                    fetched = res["data"].get("fetched", [])
                    for item in fetched:
                        tok = str(item.get("symbolToken", ""))
                        if not tok:
                            continue
                        out[tok] = {
                            "ltp": float(item.get("ltp", 0) or 0),
                            "open": float(item.get("open", 0) or 0),
                            "high": float(item.get("high", 0) or 0),
                            "low": float(item.get("low", 0) or 0),
                            "close": float(item.get("close", 0) or 0),
                            "volume": float(item.get("tradeVolume", 0) or 0),
                            "tot_buy_qty": float(item.get("totBuyQuan", 0) or 0),
                            "tot_sell_qty": float(item.get("totSellQuan", 0) or 0),
                        }
                time.sleep(0.35)
            except Exception:
                time.sleep(0.5)
        return out


angel_client = AngelClient()
