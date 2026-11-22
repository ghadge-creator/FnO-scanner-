import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from app.engine import scanner_engine

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=scanner_engine.refresh_all_zones, daemon=True).start()
    scheduler.add_job(scanner_engine.run_live_scan, "interval", seconds=12, id="live_scan", replace_existing=True)
    scheduler.add_job(scanner_engine.refresh_all_zones, "cron", day_of_week="mon-fri", hour=9, minute=10, id="morning_refresh", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="NSE F&O Scanner", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "angel_connected": scanner_engine.get_state()["angel_connected"]}

@app.get("/api/state")
def state():
    return scanner_engine.get_state()

@app.get("/api/chart/{symbol}")
def get_chart(symbol: str, tf: str = "1D"):
    iv_map = {"1D": ("ONE_DAY", 240), "1W": ("ONE_WEEK", 500), "1H": ("ONE_HOUR", 45), "15m": ("FIFTEEN_MINUTE", 15), "5m": ("FIVE_MINUTE", 5)}
    iv, days = iv_map.get(tf, ("ONE_DAY", 240))
    tok = next((str(u["token"]) for u in scanner_engine.universe if u["symbol"] == symbol), symbol)
    df = scanner_engine._get_df(symbol, tok, iv, tf, days)
    if df is None or df.empty:
        return {"candles": []}
    rows = df.tail(150)
    candles = [{"t": str(r["timestamp"])[:16], "o": round(float(r["open"]), 2), "h": round(float(r["high"]), 2), "l": round(float(r["low"]), 2), "c": round(float(r["close"]), 2), "v": float(r["volume"])} for _, r in rows.iterrows()]
    return {"symbol": symbol, "tf": tf, "candles": candles}

@app.post("/api/scan")
def force_scan():
    threading.Thread(target=scanner_engine.run_live_scan, kwargs={"force": True}, daemon=True).start()
    return {"status": "scan_started"}

@app.post("/api/refresh")
def force_refresh():
    threading.Thread(target=scanner_engine.refresh_all_zones, daemon=True).start()
    return {"status": "refresh_started"}
