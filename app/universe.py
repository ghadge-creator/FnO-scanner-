"""NSE F&O stock universe from Angel One's public Instrument Master."""
import gc
import json
import time

import requests
from logzero import logger

from . import config

CACHE = config.DATA_DIR / "universe.json"
MAX_AGE_SEC = 20 * 3600


def _fallback() -> list:
    names = json.loads(config.FNO_FALLBACK_FILE.read_text())
    return [{"symbol": n, "token": None, "yf": f"{n}.NS"} for n in names]


def _read_cache(allow_stale: bool):
    if not CACHE.exists():
        return None
    if time.time() - CACHE.stat().st_mtime > MAX_AGE_SEC and not allow_stale:
        return None
    try:
        data = json.loads(CACHE.read_text())
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def _download() -> list:
    logger.info("Downloading Angel One instrument master ...")
    r = requests.get(config.SCRIP_MASTER_URL, timeout=180)
    r.raise_for_status()
    data = json.loads(r.content)
    del r
    fno, nse = set(), {}
    for x in data:
        seg = x.get("exch_seg")
        if seg == "NFO" and x.get("instrumenttype") == "FUTSTK":
            fno.add(x.get("name"))
        elif seg == "NSE" and str(x.get("symbol", "")).endswith("-EQ"):
            nse[x.get("name")] = str(x.get("token"))
    del data
    gc.collect()
    out = [
        {"symbol": name, "token": nse[name], "yf": f"{name}.NS"}
        for name in sorted(fno)
        if name in nse
    ]
    logger.info("F&O stocks mapped to NSE cash tokens: %d", len(out))
    return out


def load_universe() -> list:
    cached = _read_cache(allow_stale=False)
    if cached:
        return cached
    try:
        out = _download()
        if len(out) >= 50:
            CACHE.write_text(json.dumps(out))
            return out
        logger.warning("Instrument master returned too few stocks (%d)", len(out))
    except Exception as e:
        logger.warning("Instrument master download failed: %s", e)
    stale = _read_cache(allow_stale=True)
    if stale:
        return stale
    logger.warning("Using local fno_stocks.json fallback list")
    return _fallback()
