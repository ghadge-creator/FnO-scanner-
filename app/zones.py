"""1-Day Demand & Supply zone detection (pure Price Action, ATR(14) only)."""
import numpy as np
import pandas as pd

BASE_MAX_BODY = 0.50   # base: |close-open| <= 0.50 * range
LEG_MIN_BODY = 0.70    # leg-out: |close-open| >= 0.70 * range
LEG_ATR_MULT = 1.5     # leg-out range >= 1.5 * ATR(14)
MAX_BASE = 3
MAX_TOUCHES = 2        # 0 = Fresh, 1-2 = Tested, >2 hidden


def atr14(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()


def detect_zones(df: pd.DataFrame) -> list:
    """df columns: date, open, high, low, close (ascending, completed candles only)."""
    if df is None or len(df) < 30:
        return []
    df = df.reset_index(drop=True)
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    dates = df["date"].astype(str).to_numpy()
    atr = atr14(df).to_numpy(dtype=float)
    n = len(df)

    rng = h - l
    body = np.abs(c - o)
    valid = rng > 0
    is_base = valid & (body <= BASE_MAX_BODY * rng)
    is_leg = valid & (body >= LEG_MIN_BODY * rng)

    zones = []
    for i in range(1, n - 1):
        li = i - 1  # leg-in candle: directional, non-base
        if not is_base[i] or is_base[li] or not valid[li] or c[li] == o[li]:
            continue
        legin_up = c[li] > o[li]

        for nb in range(1, MAX_BASE + 1):
            last = i + nb - 1
            if last >= n - 1 or not is_base[last]:
                break
            j = last + 1
            a = atr[last]
            if np.isnan(a) or a <= 0:
                continue

            leg_n = 0
            if is_leg[j] and rng[j] >= LEG_ATR_MULT * a:
                leg_n = 1
            elif (
                j + 1 < n
                and is_leg[j]
                and is_leg[j + 1]
                and (c[j] > o[j]) == (c[j + 1] > o[j + 1])
                and (max(h[j], h[j + 1]) - min(l[j], l[j + 1])) >= LEG_ATR_MULT * a
            ):
                leg_n = 2
            if leg_n == 0:
                continue

            end = j + leg_n - 1
            up = c[j] > o[j]
            b_hi = h[i : last + 1].max()
            b_lo = l[i : last + 1].min()
            if up and not c[end] > b_hi:
                continue
            if (not up) and not c[end] < b_lo:
                continue

            bodies_hi = np.maximum(o[i : last + 1], c[i : last + 1])
            bodies_lo = np.minimum(o[i : last + 1], c[i : last + 1])
            if up:
                side = "DEMAND"
                pattern = "RBR" if legin_up else "DBR"
                proximal = float(bodies_hi.max())
                distal = float(min(b_lo, l[li]))
            else:
                side = "SUPPLY"
                pattern = "RBD" if legin_up else "DBD"
                proximal = float(bodies_lo.min())
                distal = float(max(b_hi, h[li]))

            touches, dead = 0, False
            for k in range(end + 1, n):
                if side == "DEMAND":
                    if c[k] < distal:
                        dead = True
                        break
                    if l[k] <= proximal:
                        touches += 1
                else:
                    if c[k] > distal:
                        dead = True
                        break
                    if h[k] >= proximal:
                        touches += 1
            if not dead and touches <= MAX_TOUCHES:
                zones.append(
                    {
                        "side": side,
                        "pattern": pattern,
                        "proximal": round(proximal, 2),
                        "distal": round(distal, 2),
                        "freshness": "Fresh" if touches == 0 else "Tested",
                        "touches": int(touches),
                        "formed": str(dates[j]),
                    }
                )
            break  # one zone per base start
    zones.sort(key=lambda z: z["formed"], reverse=True)
    return zones


def is_hit(zone: dict, ltp: float, high: float, low: float) -> bool:
    """Trigger ONLY when live LTP touches inside the zone (no pre-touch buffer)."""
    p, d = zone["proximal"], zone["distal"]
    if zone["side"] == "DEMAND":
        return d <= ltp <= p
    return p <= ltp <= d


def in_zone(zone: dict, price) -> bool:
    if price is None:
        return False
    p, d = zone["proximal"], zone["distal"]
    return d <= price <= p if zone["side"] == "DEMAND" else p <= price <= d
