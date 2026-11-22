import re, threading, time
from datetime import datetime
import pandas as pd, pytz, yfinance as yf
from app.angel import angel_client
from app.universe import load_fno_universe
from app.zones import detect_zones_from_df, evaluate_institutional_footprint
from app.notifier import send_alert

IST = pytz.timezone("Asia/Kolkata")

def _yf_sym(s):
    c = re.sub(r"\d{2}[A-Z]{3}(FUT)?$", "", s.upper().replace("-EQ", "").strip())
    return ("M&M" if c in ("M_M", "M&M") else c) + ".NS"

class ScannerEngine:
    def __init__(self):
        self.universe = load_fno_universe()
        self.zones_1d, self.zones_mtf, self.avg_vol = [], [], {}
        self.touches, self.inst, self.alerted = [], [], set()
        self.is_refreshing, self.progress = False, "0/0"
        self.last_update = self.last_scan = "--:--:--"
        self._lock = threading.Lock()

    def is_market_open(self):
        n = datetime.now(IST)
        return n.weekday() < 5 and (9 * 60 + 15) <= (n.hour * 60 + n.minute) <= (15 * 60 + 30)

    def _get_df(self, sym, tok, iv, tf, days):
        for ex in ("NSE", "NFO"):
            df = angel_client.get_historical_candles(tok, iv, days, ex)
            if df is not None and not df.empty:
                return df
        ym = {"1D": ("1y", "1d"), "1W": ("2y", "1wk"), "1H": ("60d", "60m"), "15m": ("15d", "15m"), "5m": ("5d", "5m")}
        p, yi = ym.get(tf, ("1y", "1d"))
        try:
            h = yf.Ticker(_yf_sym(sym)).history(period=p, interval=yi)
            if h is None or h.empty: return None
            h = h.reset_index()
            tc = "Datetime" if "Datetime" in h.columns else "Date"
            return pd.DataFrame({"timestamp": pd.to_datetime(h[tc]), "open": h["Open"], "high": h["High"], "low": h["Low"], "close": h["Close"], "volume": h["Volume"].fillna(0)}).dropna()
        except Exception:
            return None

    def refresh_all_zones(self, mtf=True):
        if self.is_refreshing: return
        self.is_refreshing = True
        tot = len(self.universe)
        n1d, nmtf, nav = [], [], {}
        tfs = [("ONE_DAY", "1D", 220)] + ([("ONE_WEEK", "1W", 450), ("ONE_HOUR", "1H", 45), ("FIFTEEN_MINUTE", "15m", 12), ("FIVE_MINUTE", "5m", 5)] if mtf else [])
        try:
            angel_client.login()
            for i, u in enumerate(self.universe, 1):
                self.progress = f"{i}/{tot}"
                sym, tok = u["symbol"], str(u.get("token", ""))
                if not tok: continue
                for iv, tf, d in tfs:
                    df = self._get_df(sym, tok, iv, tf, d)
                    if df is None or df.empty: continue
                    if tf == "1D" and len(df) >= 5: nav[sym] = float(df["volume"].tail(20).mean())
                    for z in detect_zones_from_df(df, tf, 2, 180):
                        z.update({"symbol": sym, "token": tok})
                        if tf == "1D": n1d.append(z)
                        nmtf.append(z)
                    time.sleep(0.04)
                if i % 10 == 0:
                    with self._lock:
                        self.zones_1d, self.zones_mtf = list(n1d), list(nmtf)
                        self.avg_vol.update(nav)
            with self._lock:
                if n1d: self.zones_1d = n1d
                if nmtf: self.zones_mtf = nmtf
                self.avg_vol.update(nav)
                self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        finally:
            self.is_refreshing, self.progress = False, f"{tot}/{tot}"
            self.run_live_scan(force=True)

    def _quotes(self):
        toks = [str(u["token"]) for u in self.universe if u.get("token")]
        q = angel_client.get_full_quotes(toks, "NSE") or angel_client.get_full_quotes(toks, "NFO")
        if q: return q
        out = {}
        for sym, tok in {z["symbol"]: str(z["token"]) for z in (self.zones_mtf or self.zones_1d)}.items():
            try:
                h = yf.Ticker(_yf_sym(sym)).history(period="5d", interval="1d")
                if h is not None and not h.empty:
                    l = h.iloc[-1]
                    out[tok] = {"ltp": float(l["Close"]), "open": float(l["Open"]), "high": float(l["High"]), "low": float(l["Low"]), "volume": float(l["Volume"]), "tot_buy_qty": 0.0, "tot_sell_qty": 0.0}
            except Exception: pass
        return out

    def run_live_scan(self, force=False):
        if not force and not self.is_market_open(): return
        if not self.zones_1d and not self.is_refreshing:
            threading.Thread(target=self.refresh_all_zones, daemon=True).start()
            return
        qs = self._quotes()
        if not qs: return
        now_s, day_k = datetime.now(IST).strftime("%H:%M:%S"), datetime.now(IST).strftime("%Y-%m-%d")
        t1d, ih = [], []
        for z in self.zones_1d:
            q = qs.get(str(z["token"]))
            if not q or q["ltp"] <= 0: continue
            ltp, zl, zh = q["ltp"], z["zone_low"], z["zone_high"]
            px = max((zh - zl) * 0.35, ltp * 0.015)
            if (zl - px) <= ltp <= (zh + px):
                fp = evaluate_institutional_footprint(ltp, q["open"], q["high"], q["low"], q["volume"], self.avg_vol.get(z["symbol"], 0), q["tot_buy_qty"], q["tot_sell_qty"], z["zone_type"])
                t1d.append({**z, "ltp": round(ltp, 2), "touched_at": now_s, "institutional": fp})
                aid = f"{day_k}:1D:{z['symbol']}:{z['zone_type']}:{zl}"
                if aid not in self.alerted:
                    self.alerted.add(aid)
                    send_alert(f"1D {z['zone_type']}: {z['symbol']} @ {ltp}", f"Zone {zl} - {zh}")
        for z in (self.zones_mtf or self.zones_1d):
            q = qs.get(str(z["token"]))
            if not q or q["ltp"] <= 0: continue
            ltp, zl, zh = q["ltp"], z["zone_low"], z["zone_high"]
            px = max((zh - zl) * 0.35, ltp * 0.012)
            if (zl - px) <= ltp <= (zh + px):
                fp = evaluate_institutional_footprint(ltp, q["open"], q["high"], q["low"], q["volume"], self.avg_vol.get(z["symbol"], 0), q["tot_buy_qty"], q["tot_sell_qty"], z["zone_type"])
                if fp.get("is_institutional"):
                    ih.append({**z, "ltp": round(ltp, 2), "touched_at": now_s, **fp})
        ih.sort(key=lambda x: x.get("inst_score", 0), reverse=True)
        with self._lock:
            self.touches, self.inst, self.last_scan = t1d, ih, now_s

    def get_state(self):
        with self._lock:
            return {"angel_connected": angel_client.connected, "angel_status": angel_client.status_msg, "market_open": self.is_market_open(), "last_scan": self.last_scan, "last_zone_update": self.last_update, "is_refreshing": self.is_refreshing, "refresh_progress": self.progress, "total_zones_1d": len(self.zones_1d), "demand_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "DEMAND"), "supply_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "SUPPLY"), "total_zones_mtf": len(self.zones_mtf), "touches": self.touches, "institutional": self.inst}

scanner_engine = ScannerEngine()
