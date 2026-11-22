import json
import os
from typing import Dict, List


def load_fno_universe() -> List[Dict]:
    """
    Loads F&O stock list from fno_stocks.json in the project root.
    Supports list of dicts or dict mapping symbol -> token.
    """
    paths = ["fno_stocks.json", os.path.join("data", "fno_stocks.json")]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                out: List[Dict] = []
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            sym = item.get("symbol") or item.get("name") or item.get("tradingsymbol") or ""
                            tok = str(item.get("token") or item.get("symboltoken") or item.get("symbolToken") or "")
                            if sym and tok:
                                out.append({"symbol": sym, "token": tok})
                elif isinstance(raw, dict):
                    for sym, val in raw.items():
                        if isinstance(val, dict):
                            tok = str(val.get("token") or val.get("symboltoken") or "")
                        else:
                            tok = str(val)
                        if sym and tok:
                            out.append({"symbol": sym, "token": tok})
                if out:
                    return out
            except Exception:
                pass
    return []
