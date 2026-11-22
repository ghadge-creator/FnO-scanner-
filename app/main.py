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
    # Initial background zone build on startup
    threading.Thread(target=scanner_engine.refresh_all_zones, daemon=True).start()
    # Scan every 12 seconds during market hours
    scheduler.add_job(scanner_engine.run_live_scan, "interval", seconds=12, id="live_scan", replace_existing=True)
    # Refresh zones at 09:10 AM IST Mon-Fri
    scheduler.add_job(scanner_engine.refresh_all_zones, "cron", day_of_week="mon-fri", hour=9, minute=10, id="morning_refresh", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="NSE F&O 1D & Institutional Scanner", lifespan=lifespan)
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


@app.post("/api/scan")
def force_scan():
    threading.Thread(target=scanner_engine.run_live_scan, kwargs={"force": True}, daemon=True).start()
    return {"status": "scan_started"}


@app.post("/api/refresh")
def force_refresh():
    threading.Thread(target=scanner_engine.refresh_all_zones, daemon=True).start()
    return {"status": "refresh_started"}
