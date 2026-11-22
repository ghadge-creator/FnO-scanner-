import re, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pandas as pd, pytz, yfinance as yf
from app.angel import angel_client
from app.universe import load_fno_universe
from app.zones import detect_zones_from_df
from app.notifier import send_alert

IST = pytz.timezone("Asia/Kolkata")

def _yf_sym(s):
    c = re.sub(r"\d{2}[A-Z]{3}(FUT)?$", "", s.upper().replace("-EQ", "").strip())
    return ("M&M" if c in ("M_M", "M&M") else c) + ".NS"

class ScannerEngine:
    def __init__(self):
        self.universe = load_fno_universe()
        self.zones_1d, self.zones_mtf, self.avg_vol = [], [], {}
        self.inst_from_df = []
        self.touches, self.inst, self.alerted = [], [], set()
        self.is_refreshing, self.progress = False, "0/0"
        self.last_update = self.last_scan = "--:--:--"
        self._lock = threading.Lock()

    def is_market_open(self):
        n = datetime.now(IST)
        return n.weekday() < 5 and (9 * 60 + 15) <= (n.hour * 60 + n.minute) <= (15 * 60 + 30)

    def _get_df(self, sym, tok, iv, tf, days):
        if tok and tok.isdigit():
            df = angel_client.get_historical_candles(tok, iv, days, "NSE")
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

    def _check_df_inst(self, sym, tok, tf, df):
        if df is None or len(df) < 15: return None
        last = df.iloc[-1]
        av = float(df["volume"].iloc[-21:-1].mean()) if len(df) >= 21 else float(df["volume"].mean())
        vol = float(last["volume"])
        vr = round(vol / av, 2) if av > 0 else 1.0
        op, cl, hi, lo = float(last["open"]), float(last["close"]), float(last["high"]), float(last["low"])
        chg = ((cl - op) / max(op, 1e-6)) * 100.0
        if vr >= 1.35 or abs(chg) >= 1.6:
            if cl > op and (vr >= 1.3 or chg >= 1.6):
                return {"symbol": sym, "token": tok, "timeframe": tf, "zone_type": "DEMAND", "zone_low": round(lo, 2), "zone_high": round(hi, 2), "ltp": round(cl, 2), "touched_at": str(last["timestamp"])[:16], "is_institutional": True, "inst_side": "INST_BUYING", "inst_score": min(99, int(52 + vr * 14 + chg * 5)), "vol_ratio": vr, "buy_sell_ratio": round(max(1.2, vr), 2), "sell_buy_ratio": 1.0, "reasons": [f"Vol {vr}x", f"+{round(chg, 2)}%"]}
            if cl < op and (vr >= 1.3 or chg <= -1.6):
                return {"symbol": sym, "token": tok, "timeframe": tf, "zone_type": "SUPPLY", "zone_low": round(lo, 2), "zone_high": round(hi, 2), "ltp": round(cl, 2), "touched_at": str(last["timestamp"])[:16], "is_institutional": True, "inst_side": "INST_SELLING", "inst_score": min(99, int(52 + vr * 14 + (-chg) * 5)), "vol_ratio": vr, "buy_sell_ratio": 1.0, "sell_buy_ratio": round(max(1.2, vr), 2), "reasons": [f"Vol {vr}x", f"{round(chg, 2)}%"]}
        return None

    def _load_one_1d(self, u):
        sym, tok = u["symbol"], str(u.get("token", ""))
        df = self._get_df(sym, tok, "ONE_DAY", "1D", 220)
        if df is None or df.empty: return sym, 0.0, [], None
        av = float(df["volume"].tail(20).mean()) if len(df) >= 5 else 0.0
        zs = detect_zones_from_df(df, "1D", 3, 200)
        for z in zs: z.update({"symbol": sym, "token": tok})
        ih = self._check_df_inst(sym, tok, "1D", df)
        return sym, av, zs, ih

    def refresh_all_zones(self, mtf=True):
        if self.is_refreshing: return
        self.is_refreshing = True
        tot = len(self.universe)
        n1d, nav, df_inst = [], {}, []
        try:
            angel_client.login()
            done = 0
            with ThreadPoolExecutor(max_workers=8) as ex:
                for sym, av, zs, ih in ex.map(self._load_one_1d, self.universe):
                    done += 1
                    self.progress = f"1D: {done}/{tot}"
                    if av > 0: nav[sym] = av
                    if zs: n1d.extend(zs)
                    if ih: df_inst.append(ih)
                    if done % 25 == 0:
                        with self._lock:
                            self.zones_1d = list(n1d)
                            self.avg_vol.update(nav)
                            self.inst_from_df = list(df_inst)
            with self._lock:
                if n1d: self.zones_1d = n1d
                self.avg_vol.update(nav)
                self.inst_from_df = df_inst
                self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            self.run_live_scan(force=True)

            if mtf:
                nmtf = list(n1d)
                tfs = [("ONE_WEEK", "1W", 450), ("ONE_HOUR", "1H", 45), ("FIFTEEN_MINUTE", "15m", 12), ("FIVE_MINUTE", "5m", 5)]
                for i, u in enumerate(self.universe, 1):
                    self.progress = f"All-TF: {i}/{tot}"
                    sym, tok = u["symbol"], str(u.get("token", ""))
                    for iv, tf, d in tfs:
                        df = self._get_df(sym, tok, iv, tf, d)
                        if df is not None and not df.empty:
                            for z in detect_zones_from_df(df, tf, 1, 140):
                                z.update({"symbol": sym, "token": tok})
                                nmtf.append(z)
                            ih2 = self._check_df_inst(sym, tok, tf, df)
                            if ih2: df_inst.append(ih2)
                    if i % 20 == 0:
                        with self._lock:
                            self.zones_mtf = list(nmtf)
                            self.inst_from_df = list(df_inst)
                with self._lock:
                    if nmtf: self.zones_mtf = nmtf
                    self.inst_from_df = df_inst
        finally:
            self.is_refreshing, self.progress = False, f"{tot}/{tot}"
            self.run_live_scan(force=True)

    def _quotes(self):
        num_toks = [str(u["token"]) for u in self.universe if str(u.get("token", "")).isdigit()]
        q = angel_client.get_full_quotes(num_toks, "NSE") if num_toks else {}
        if q: return q
        items = [(u["symbol"], str(u["token"])) for u in self.universe if u.get("token")]
        def fetch_one(pair):
            sym, tok = pair
            try:
                h = yf.Ticker(_yf_sym(sym)).history(period="5d", interval="1d")
                if h is not None and not h.empty:
                    l = h.iloc[-1]
                    return tok, {"ltp": float(l["Close"]), "open": float(l["Open"]), "high": float(l["High"]), "low": float(l["Low"]), "volume": float(l["Volume"]), "tot_buy_qty": 0.0, "tot_sell_qty": 0.0}
            except Exception: pass
            return tok, None
        out = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            for tok, val in ex.map(fetch_one, items):
                if val: out[tok] = val
        return out

    def run_live_scan(self, force=False):
        if not force and not self.is_market_open(): return
        if not self.zones_1d and not self.is_refreshing:
            threading.Thread(target=self.refresh_all_zones, daemon=True).start()
            return
        qs = self._quotes()
        if not qs: return
        now_s, day_k = datetime.now(IST).strftime("%H:%M:%S"), datetime.now(IST).strftime("%Y-%m-%d")

        best_1d = {}
        for z in self.zones_1d:
            q = qs.get(str(z["token"]))
            if not q or q["ltp"] <= 0: continue
            ltp, zl, zh = q["ltp"], z["zone_low"], z["zone_high"]
            px = max((zh - zl) * 0.5, ltp * 0.03)
            if (zl - px) <= ltp <= (zh + px):
                prev = best_1d.get(z["symbol"])
                if not prev or z["strength"] > prev["strength"]:
                    best_1d[z["symbol"]] = {**z, "ltp": round(ltp, 2), "touched_at": now_s}
                aid = f"{day_k}:1D:{z['symbol']}:{z['zone_type']}:{zl}"
                if aid not in self.alerted:
                    self.alerted.add(aid)
                    send_alert(f"1D {z['zone_type']}: {z['symbol']} @ {ltp}", f"Zone {zl} - {zh}")

        inst_map = {f"{x['symbol']}:{x['timeframe']}": dict(x) for x in self.inst_from_df}
        for u in self.universe:
            sym, tok = u["symbol"], str(u.get("token", ""))
            q = qs.get(tok)
            if not q or q.get("ltp", 0) <= 0: continue
            ltp, op, hi, lo = float(q["ltp"]), float(q.get("open", 0) or 0), float(q.get("high", 0) or 0), float(q.get("low", 0) or 0)
            vol, av = float(q.get("volume", 0) or 0), float(self.avg_vol.get(sym, 0) or 0)
            tb, ts = float(q.get("tot_buy_qty", 0) or 0), float(q.get("tot_sell_qty", 0) or 0)
            vr = round(vol / av, 2) if (av > 0 and vol > 0) else 1.0
            bsr = round(tb / max(ts, 1.0), 2) if tb > 0 else 1.0
            sbr = round(ts / max(tb, 1.0), 2) if ts > 0 else 1.0
            chg = ((ltp - op) / max(op, 1e-6)) * 100.0 if op > 0 else 0.0
            if vr >= 1.35 or bsr >= 1.6 or sbr >= 1.6 or abs(chg) >= 1.8:
                is_buy = (chg >= 0 and bsr >= sbr) or bsr >= 1.7
                side = "INST_BUYING" if is_buy else "INST_SELLING"
                sc = min(99, int(55 + vr * 12 + abs(chg) * 5 + (15 if max(bsr, sbr) >= 1.5 else 0)))
                best_1d[z["symbol"]] = {**z, "ltp": round(ltp, 2), "touched_at": now_s}
                aid = f"{day_k}:1D:{z['symbol']}:{z['zone_type']}:{zl}"
                if aid not in self.alerted:
                    self.alerted.add(aid)
                    send_alert(f"1D {z['zone_type']}: {z['symbol']} @ {ltp}", f"Zone {zl} - {zh}")

        inst_map = {f"{x['symbol']}:{x['timeframe']}": dict(x) for x in self.inst_from_df}
        for u in self.universe:
            sym, tok = u["symbol"], str(u.get("token", ""))
            q = qs.get(tok)
            if not q or q.get("ltp", 0) <= 0: continue
            ltp, op, hi, lo = float(q["ltp"]), float(q.get("open", 0) or 0), float(q.get("high", 0) or 0), float(q.get("low", 0) or 0)
            vol, av = float(q.get("volume", 0) or 0), float(self.avg_vol.get(sym, 0) or 0)
            tb, ts = float(q.get("tot_buy_qty", 0) or 0), float(q.get("tot_sell_qty", 0) or 0)
            vr = round(vol / av, 2) if (av > 0 and vol > 0) else 1.0
            bsr = round(tb / max(ts, 1.0), 2) if tb > 0 else 1.0
            sbr = round(ts / max(tb, 1.0), 2) if ts > 0 else 1.0
            chg = ((ltp - op) / max(op, 1e-6)) * 100.0 if op > 0 else 0.0
            if vr >= 1.35 or bsr >= 1.6 or sbr >= 1.6 or abs(chg) >= 1.8:
                is_buy = (chg >= 0 and bsr >= sbr) or bsr >= 1.7
                side = "INST_BUYING" if is_buy else "INST_SELLING"
                sc = min(99, int(55 + vr * 12 + abs(chg) * 5 + (15 if max(bsr, sbr) >= 1.5 else 0)))
Use code with caution.
inst_map[f"{sym}:1D"] = {"symbol": sym, "token": tok, "timeframe": "1D", "zone_type": "DEMAND" if is_buy else "SUPPLY", "zone_low": round(lo or ltp, 2), "zone_high": round(hi or ltp, 2), "ltp": round(ltp, 2), "touched_at": now_s, "is_institutional": True, "inst_side": side, "inst_score": sc, "vol_ratio": vr, "buy_sell_ratio": bsr, "sell_buy_ratio": sbr, "reasons": [f"Vol {vr}x", f"Buy/Sell {bsr if is_buy else sbr}x"]}
t1d = sorted(best_1d.values(), key=lambda x: x.get("strength", 0), reverse=True)
ih = sorted(inst_map.values(), key=lambda x: x.get("inst_score", 0), reverse=True)
with self._lock:
self.touches, self.inst, self.last_scan = t1d, ih, now_s
def get_state(self):
with self._lock:
return {"angel_connected": angel_client.connected, "angel_status": angel_client.status_msg, "market_open": self.is_market_open(), "last_scan": self.last_scan, "last_zone_update": self.last_update, "is_refreshing": self.is_refreshing, "refresh_progress": self.progress, "total_zones_1d": len(self.zones_1d), "demand_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "DEMAND"), "supply_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "SUPPLY"), "total_zones_mtf": len(self.zones_mtf), "touches": self.touches, "institutional": self.inst}
scanner_engine = ScannerEngine()
lf.touches, self.inst, self.last_scan = t1d, ih, now_s
def get_state(self):
with self._lock:
return {"angel_connected": angel_client.connected, "angel_status": angel_client.status_msg, "market_open": self.is_market_open(), "last_scan": self.last_scan, "last_zone_update": self.last_update, "is_refreshing": self.is_refreshing, "refresh_progress": self.progress, "total_zones_1d": len(self.zones_1d), "demand_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "DEMAND"), "supply_zones_1d": sum(1 for z in self.zones_1d if z["zone_type"] == "SUPPLY"), "total_zones_mtf": len(self.zones_mtf), "touches": self.touches, "institutional": self.inst}
scanner_engine = ScannerEngine()
---
#### 3. `static/index.html` (Single Small Box)
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>NSE F&O Scanner</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0;font-family:sans-serif}
    body{background:#0b0f17;color:#e5e7eb;overflow-x:hidden}
    .top{background:#111827;padding:12px 14px 8px;border-bottom:1px solid #1f2937;position:sticky;top:0;z-index:20}
    .row{display:flex;justify-content:space-between;font-size:12px;color:#9ca3af;margin-bottom:6px}
    .ok{color:#10b981}.warn{color:#f59e0b}
    .tabs{display:flex;background:#111827;border-bottom:1px solid #1f2937}
    .tab{flex:1;text-align:center;padding:10px 4px;font-size:13px;font-weight:700;color:#9ca3af;border-bottom:3px solid transparent}
    .tab.on{color:#60a5fa;border-bottom-color:#3b82f6}
    .bdg{background:#1f2937;color:#fff;padding:1px 6px;border-radius:10px;font-size:11px}
    .wrap{display:flex;width:200vw;transition:transform .25s ease}
    .pg{width:100vw;min-height:85vh;padding:12px 14px 40px}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
    button{border:none;border-radius:10px;padding:10px;font-size:13px;font-weight:700;cursor:pointer}
    .b1{background:#2563eb;color:#fff}.b2{background:#1f2937;color:#e5e7eb;border:1px solid #374151}
    .bt{background:#1f2937;color:#f87171;border:1px solid #374151;font-size:12px;padding:8px}.bt.on{color:#34d399;border-color:#059669}
    .meta{font-size:11px;color:#9ca3af;margin-bottom:10px}
    .pills{display:flex;gap:6px;overflow-x:auto;margin-bottom:12px}
    .pill{flex:1;text-align:center;padding:8px 10px;border-radius:10px;background:#1f2937;color:#9ca3af;font-size:12px;font-weight:700}
    .pill.on{background:#f3f4f6;color:#111827}
    .card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:13px;margin-bottom:10px}
    .ctop{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
    .sym{font-size:17px;font-weight:800;color:#fff}
    .td{background:rgba(16,185,129,.18);color:#34d399;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700}
    .ts{background:rgba(239,68,68,.18);color:#f87171;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700}
    .cmid{display:flex;justify-content:space-between;font-size:13px;color:#d1d5db;margin-bottom:5px}
    .empty{text-align:center;color:#9ca3af;font-size:13px;padding:30px 15px}
    .modal{display:none;position:fixed;inset:0;background:#0b0f17;z-index:99;flex-direction:column}.modal.on{display:flex}
    .mhdr{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:#111827;border-bottom:1px solid #1f2937}
    .ibar{display:none;padding:6px 12px;background:#172033;font-size:12px;font-weight:700}
    .indb{display:flex;gap:6px;padding:6px 12px;background:#0f172a;border-bottom:1px solid #1f2937}
    .ibtn{padding:4px 9px;font-size:11px;border-radius:6px;background:#1f2937;color:#9ca3af}.ibtn.on{background:#2563eb;color:#fff}
    #cvs{flex:1;width:100vw;display:block;touch-action:none}
  </style>
</head>
<body>
  <div class="top">
    <div class="row"><div>Angel One: <b id="ag" class="warn">Checking...</b></div><div>Market: <b id="mk">--</b></div></div>
    <div class="row" style="margin:0"><div>Last Scan: <b id="ls">--:--:--</b></div><div>1D: <b id="tc">0</b> | Inst: <b id="ic">0</b></div></div>
    <div id="rb" style="font-size:11px;color:#60a5fa;display:none;margin-top:4px"></div>
  </div>
  <div class="tabs">
    <div class="tab on" id="t0" onclick="go(0)">1D Demand & Supply <span class="bdg" id="b0">0</span></div>
    <div class="tab" id="t1" onclick="go(1)">🔥 Inst. Orders <span class="bdg" id="b1">0</span></div>
  </div>
  <div class="wrap" id="wp">
    <div class="pg">
      <div class="grid2"><button class="b1" onclick="scan()">▶ Test Live Scan Now</button><button class="b2" onclick="ref()">↻ Refresh Zones</button></div>
      <div class="grid2"><button class="bt" id="sb" onclick="togS()">🔇 Sound: OFF</button><button class="bt" id="ab" onclick="togA()">🔕 Alerts: OFF</button></div>
      <div class="meta" id="mt">Loading zones...</div>
      <div class="pills"><div class="pill on" onclick="sf1('ALL',this)">All</div><div class="pill" onclick="sf1('DEMAND',this)">1D Demand</div><div class="pill" onclick="sf1('SUPPLY',this)">1D Supply</div></div>
      <div id="l1"></div>
    </div>
    <div class="pg">
      <div class="pills"><div class="pill on" onclick="stf('ALL',this)">All TF</div><div class="pill" onclick="stf('5m',this)">5m</div><div class="pill" onclick="stf('15m',this)">15m</div><div class="pill" onclick="stf('1H',this)">1H</div><div class="pill" onclick="stf('1D',this)">1D</div><div class="pill" onclick="stf('1W',this)">1W</div></div>
      <div class="pills"><div class="pill on" onclick="ssd('ALL',this)">All</div><div class="pill" onclick="ssd('INST_BUYING',this)">🟢 Inst. Buy</div><div class="pill" onclick="ssd('INST_SELLING',this)">🔴 Inst. Sell</div></div>
      <div id="l2"></div>
    </div>
  </div>
  <div class="modal" id="md">
    <div class="mhdr"><div><b id="m1" style="font-size:15px">--</b><div id="m2" style="font-size:11px;color:#9ca3af">--</div></div><div style="display:flex;gap:6px"><button class="b2" style="padding:6px 10px" onclick="zm(-12)">＋</button><button class="b2" style="padding:6px 10px" onclick="zm(12)">－</button><button class="b2" style="padding:6px 10px" onclick="cls()">✕</button></div></div>
    <div class="ibar" id="ib"></div>
    <div class="indb"><button class="ibtn on" onclick="ti('e20',this)">EMA 20</button><button class="ibtn on" onclick="ti('e50',this)">EMA 50</button><button class="ibtn on" onclick="ti('vol',this)">Volume</button></div>
    <canvas id="cvs"></canvas>
  </div>
  <script src="/static/app.js?v=105"></script>
</body>
</html>
