import struct
import threading
import zlib
from contextlib import asynccontextmanager
from functools import lru_cache

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from logzero import logger

from . import config, db
from .engine import IST, engine

scheduler = BackgroundScheduler(timezone=IST)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    threading.Thread(target=engine.startup, daemon=True).start()
    # 08:55 IST every morning: refresh jwtToken + feedToken
    scheduler.add_job(engine.login, CronTrigger(hour=8, minute=55, timezone=IST), id="login",
                      misfire_grace_time=600)
    # 08:50 IST: refresh instrument master / F&O universe
    scheduler.add_job(engine.reload_universe, CronTrigger(hour=8, minute=50, timezone=IST),
                      id="universe", misfire_grace_time=600)
    # 09:00 IST Mon-Fri: recompute all 1-Day zones
    scheduler.add_job(engine.refresh_zones, CronTrigger(day_of_week="mon-fri", hour=9, minute=0,
                      timezone=IST), id="zones", misfire_grace_time=600)
    # Live scan (only works inside 09:15-15:30 IST Mon-Fri)
    scheduler.add_job(engine.scan_live, IntervalTrigger(seconds=config.SCAN_INTERVAL_SEC),
                      id="scan", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="1D F&O Demand & Supply Scanner", lifespan=lifespan)


# ---------------- API ----------------
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/state")
def api_state():
    return JSONResponse(
        {"status": engine.status(), "touches": engine.live_touches()},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/refresh-zones")
def api_refresh():
    return {"started": engine.refresh_zones_async()}


@app.post("/api/test-scan")
def api_test_scan():
    result = engine.test_scan()
    if result is None:
        return {"ok": False, "message": "Zones are not ready yet. Tap 'Refresh 1D Zones' and wait.",
                "touches": []}
    return {"ok": True, "message": f"{len(result)} zone touches on latest closing data",
            "touches": result}


@app.get("/api/chart/{symbol}")
def api_chart(symbol: str, live: int = 0):
    return JSONResponse({"symbol": symbol, "candles": engine.chart_data(symbol, bool(live))},
                        headers={"Cache-Control": "no-store"})


# ---------------- PWA files ----------------
@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.json")
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@lru_cache(maxsize=8)
def make_icon(size: int) -> bytes:
    """Pure-Python PNG icon: dark tile with a green and a red candle."""
    bg, green, red = (11, 18, 32), (34, 197, 94), (239, 68, 68)
    s = size / 512.0
    rows = [bytearray(bytes(bg) * size) for _ in range(size)]

    def rect(x0, y0, x1, y1, color):
        a, b = int(x0 * s), int(x1 * s)
        for y in range(int(y0 * s), min(int(y1 * s), size)):
            rows[y][a * 3 : b * 3] = bytes(color) * (b - a)

    rect(150, 190, 160, 440, green)   # green wick
    rect(110, 260, 200, 400, green)   # green body
    rect(352, 90, 362, 350, red)      # red wick
    rect(312, 140, 402, 290, red)     # red body
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


@app.get("/icon-192.png")
def icon192():
    return Response(make_icon(192), media_type="image/png")


@app.get("/icon-512.png")
def icon512():
    return Response(make_icon(512), media_type="image/png")


@app.get("/apple-touch-icon.png")
def apple_icon():
    return Response(make_icon(180), media_type="image/png")


app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
