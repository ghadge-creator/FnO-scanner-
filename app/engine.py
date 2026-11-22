import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
import pytz

from app.angel import angel_client
from app.universe import load_fno_universe
from app.zones import detect_zones_from_df, evaluate_institutional_footprint
from app.notifier import send_alert

IST = pytz.timezone("Asia/Kolkata")


class ScannerEngine:
    def __init__(self):
        self.universe: List[Dict] = load_fno_universe()
        self.zones_1d: List[Dict] = []
        self.zones_mtf: List[Dict] = []  # 5m, 15m, 1H, 1D, 1W
        self.avg_vol_map: Dict[str, float] = {}
        self.active_touches_1d: List[Dict] = []
        self.institutional_signals: List[Dict] = []
        self.is_refreshing: bool = False
        self.refresh_progress: str = "0/0"
        self.last_zone_update: str = "--:--:--"
        self.last_scan_time: str = "--:--:--"
        self.alerted_keys: set = set()
        self._lock = threading.Lock()

    def is_market_open(self) -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        return (9 * 60 + 15) <= t <= (15 * 60 + 30)

    def refresh_all_zones(self, include_intraday_tf: bool = True):
        if self.is_refreshing:
            return
        self.is_refreshing = True
        total = len(self.universe)
        new_1d: List[Dict] = []
        new_mtf: List[Dict] = []
        new_avg_vol: Dict[str, float] = {}

        tf_specs = [("ONE_DAY", "1D", 220)]
        if include_intraday_tf:
            tf_specs.extend(
                [
                    ("ONE_WEEK", "1W", 450),
                    ("ONE_HOUR", "1H", 45),
                    ("FIFTEEN_MINUTE", "15m", 12),
                    ("FIVE_MINUTE", "5m", 5),
                ]
            )

        try:
            angel_client.login()
            for idx, item in enumerate(self.universe, start=1):
                self.refresh_progress = f"{idx}/{total}"
                sym = item["symbol"]
                tok = str(item.get("token", ""))
                if not tok:
                    continue

                for interval, tf_label, days in tf_specs:
                    df = angel_client.get_historical_candles(
                        symbol_token=tok,
                        interval=interval,
                        days=days,
                        exchange="NFO",
                    )
                    if df is None or df.empty:
                        continue

                    if tf_label == "1D" and len(df) >= 5:
                        new_avg_vol[sym] = float(df["volume"].tail(20).mean())

                    detected = detect_zones_from_df(
                        df,
                        timeframe=tf_label,
                        max_zones_per_side=2,
                        lookback_candles=150,
                    )
                    for z in detected:
                        z["symbol"] = sym
                        z["token"] = tok
                        if tf_label == "1D":
                            new_1d.append(z)
                        new_mtf.append(z)

                    time.sleep(0.22)

            with self._lock:
                if new_1d:
                    self.zones_1d = new_1d
                if new_mtf:
                    self.zones_mtf = new_mtf
                if new_avg_vol:
                    self.avg_vol_map.update(new_avg_vol)
                self.last_zone_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        finally:
            self.is_refreshing = False
            self.refresh_progress = f"{total}/{total}"

    def run_live_scan(self, force: bool = False):
        if not force and not self.is_market_open():
            return

        if not self.zones_1d and not self.is_refreshing:
            threading.Thread(target=self.refresh_all_zones, daemon=True).start()
            return

        tokens = [str(u["token"]) for u in self.universe if u.get("token")]
        quotes = angel_client.get_full_quotes(tokens, exchange="NFO")
        if not quotes:
            return

        now_str = datetime.now(IST).strftime("%H:%M:%S")
        today_key = datetime.now(IST).strftime("%Y-%m-%d")
        touches_1d: List[Dict] = []
        inst_hits: List[Dict] = []

        # 1) Screen 1: Original 1D Demand & Supply Zone Touches (100% intact)
        for z in self.zones_1d:
            tok = str(z.get("token", ""))
            q = quotes.get(tok)
            if not q or q.get("ltp", 0) <= 0:
                continue
            ltp = q["ltp"]
            z_low = z["zone_low"]
            z_high = z["zone_high"]
            buffer = (z_high - z_low) * 0.15

            if (z_low - buffer) <= ltp <= (z_high + buffer):
                fp = evaluate_institutional_footprint(
                    ltp=ltp,
                    day_open=q.get("open", ltp),
                    day_high=q.get("high", ltp),
                    day_low=q.get("low", ltp),
                    day_volume=q.get("volume", 0),
                    avg_daily_vol=self.avg_vol_map.get(z["symbol"], 0),
                    tot_buy_qty=q.get("tot_buy_qty", 0),
                    tot_sell_qty=q.get("tot_sell_qty", 0),
                    zone_type=z["zone_type"],
                )
                hit = {
                    **z,
                    "ltp": round(ltp, 2),
                    "touched_at": now_str,
                    "institutional": fp,
                }
                touches_1d.append(hit)

                alert_id = f"{today_key}:1D:{z['symbol']}:{z['zone_type']}:{z_low}"
                if alert_id not in self.alerted_keys:
                    self.alerted_keys.add(alert_id)
                    try:
                        send_alert(
                            f"1D {z['zone_type']} Touch: {z['symbol']} @ {ltp}",
                            f"Zone {z_low} - {z_high}",
                        )
                    except Exception:
                        pass

        # 2) Screen 2: All-Timeframe (5m, 15m, 1H, 1D, 1W) Institutional Buying & Selling
        source_zones = self.zones_mtf if self.zones_mtf else self.zones_1d
        for z in source_zones:
            tok = str(z.get("token", ""))
            q = quotes.get(tok)
            if not q or q.get("ltp", 0) <= 0:
                continue
            ltp = q["ltp"]
            z_low = z["zone_low"]
            z_high = z["zone_high"]
            buffer = (z_high - z_low) * 0.20

            if (z_low - buffer) <= ltp <= (z_high + buffer):
                fp = evaluate_institutional_footprint(
                    ltp=ltp,
                    day_open=q.get("open", ltp),
                    day_high=q.get("high", ltp),
                    day_low=q.get("low", ltp),
                    day_volume=q.get("volume", 0),
                    avg_daily_vol=self.avg_vol_map.get(z["symbol"], 0),
                    tot_buy_qty=q.get("tot_buy_qty", 0),
                    tot_sell_qty=q.get("tot_sell_qty", 0),
                    zone_type=z["zone_type"],
                )
                if fp.get("is_institutional"):
                    inst_hits.append(
                        {
                            **z,
                            "ltp": round(ltp, 2),
                            "touched_at": now_str,
                            "inst_side": fp["inst_side"],
                            "inst_score": fp["inst_score"],
                            "vol_ratio": fp["vol_ratio"],
                            "buy_sell_ratio": fp["buy_sell_ratio"],
                            "sell_buy_ratio": fp["sell_buy_ratio"],
                            "reasons": fp["reasons"],
                        }
                    )

        inst_hits.sort(key=lambda x: x.get("inst_score", 0), reverse=True)

        with self._lock:
            self.active_touches_1d = touches_1d
            self.institutional_signals = inst_hits
            self.last_scan_time = now_str

    def get_state(self) -> Dict:
        with self._lock:
            d_cnt = sum(1 for z in self.zones_1d if z["zone_type"] == "DEMAND")
            s_cnt = sum(1 for z in self.zones_1d if z["zone_type"] == "SUPPLY")
            return {
                "angel_connected": angel_client.connected,
                "angel_status": angel_client.status_msg,
                "market_open": self.is_market_open(),
                "last_scan": self.last_scan_time,
                "last_zone_update": self.last_zone_update,
                "is_refreshing": self.is_refreshing,
                "refresh_progress": self.refresh_progress,
                "total_zones_1d": len(self.zones_1d),
                "demand_zones_1d": d_cnt,
                "supply_zones_1d": s_cnt,
                "total_zones_mtf": len(self.zones_mtf),
                "touches": self.active_touches_1d,
                "institutional": self.institutional_signals,
            }


scanner_engine = ScannerEngine()
