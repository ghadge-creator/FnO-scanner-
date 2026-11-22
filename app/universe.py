import json, os, requests

def load_fno_universe():
    out, seen = [], set()
    for p in ("fno_stocks.json", "data/fno_stocks.json"):
        if os.path.exists(p):
            try:
                raw = json.load(open(p, "r", encoding="utf-8"))
                items = raw if isinstance(raw, list) else [{"symbol": k, **(v if isinstance(v, dict) else {"token": v})} for k, v in raw.items()]
                for it in items:
                    if not isinstance(it, dict): continue
                    sym = str(it.get("symbol") or it.get("name") or it.get("tradingsymbol") or it.get("sym") or "").strip()
                    tok = str(it.get("token") or it.get("symboltoken") or it.get("symbolToken") or it.get("tok") or "").strip()
                    if sym and tok and sym not in seen:
                        seen.add(sym)
                        out.append({"symbol": sym, "token": tok})
            except Exception:
                pass
    if out:
        return out

    try:
        r = requests.get("https://angelbroking.com", timeout=20)
        data = r.json()
        fno_names = {d["name"] for d in data if d.get("exch_seg") == "NFO" and d.get("instrumenttype") == "FUTSTK" and d.get("name")}
        for d in data:
            if d.get("exch_seg") == "NSE" and d.get("symbol", "").endswith("-EQ") and d.get("name") in fno_names:
                nm = d["name"]
                if nm not in seen:
                    seen.add(nm)
                    out.append({"symbol": nm, "token": str(d["token"])})
    except Exception:
        pass
    return out
