from typing import Dict, List, Optional
import numpy as np
import pandas as pd


def detect_zones_from_df(
    df: pd.DataFrame,
    timeframe: str = "1D",
    max_zones_per_side: int = 2,
    lookback_candles: int = 160,
) -> List[Dict]:
    """
    Detects fresh Demand (RBR / DBR) and Supply (DBD / RBD) zones on any timeframe
    (5m, 15m, 1H, 1D, 1W) using impulsive leg-out (>1.5x ATR) and freshness check.
    """
    if df is None or len(df) < 25:
        return []

    data = df.tail(lookback_candles).copy().reset_index(drop=True)
    n = len(data)

    high = data["high"].values
    low = data["low"].values
    open_p = data["open"].values
    close_p = data["close"].values
    vol = data["volume"].values if "volume" in data.columns else np.zeros(n)

    prev_close = np.roll(close_p, 1)
    prev_close[0] = close_p[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().bfill().values
    avg_vol = pd.Series(vol).rolling(20, min_periods=5).mean().bfill().values

    body = np.abs(close_p - open_p)
    full_range = np.maximum(high - low, 1e-6)
    body_ratio = body / full_range

    demand_zones: List[Dict] = []
    supply_zones: List[Dict] = []

    # Scan backwards from recent completed candles
    for i in range(n - 3, 2, -1):
        curr_atr = max(atr[i], 1e-6)
        # Base candle check: small body (< 55% of range)
        if body_ratio[i] > 0.55:
            continue

        # Leg-out candle (i+1) or 2-candle combined impulse
        leg_move = close_p[i + 1] - open_p[i + 1]
        leg_range = high[i + 1] - low[i + 1]
        leg_vol_ratio = (vol[i + 1] / avg_vol[i + 1]) if avg_vol[i + 1] > 0 else 1.0

        # Bullish Leg-Out -> DEMAND ZONE
        if leg_move > 1.35 * curr_atr and close_p[i + 1] > high[i]:
            z_low = float(min(low[i], low[i + 1]))
            z_high = float(max(open_p[i], close_p[i]))
            if z_high <= z_low:
                z_high = float(high[i])

            # Check freshness: future candles after i+1 must not break below z_low
            future_lows = low[i + 2 :]
            if len(future_lows) > 0 and np.min(future_lows) < z_low:
                continue

            ts_str = str(data["timestamp"].iloc[i])[:16]
            strength = round(min(99.0, 55.0 + (leg_move / curr_atr) * 12.0 + min(leg_vol_ratio, 3.0) * 6.0), 1)
            demand_zones.append(
                {
                    "timeframe": timeframe,
                    "zone_type": "DEMAND",
                    "zone_low": round(z_low, 2),
                    "zone_high": round(z_high, 2),
                    "origin_ts": ts_str,
                    "strength": strength,
                    "leg_vol_ratio": round(float(leg_vol_ratio), 2),
                    "avg_vol": float(avg_vol[-1]) if avg_vol[-1] > 0 else 0.0,
                }
            )

        # Bearish Leg-Out -> SUPPLY ZONE
        elif (-leg_move) > 1.35 * curr_atr and close_p[i + 1] < low[i]:
            z_high = float(max(high[i], high[i + 1]))
            z_low = float(min(open_p[i], close_p[i]))
            if z_low >= z_high:
                z_low = float(low[i])

            # Check freshness: future candles after i+1 must not break above z_high
            future_highs = high[i + 2 :]
            if len(future_highs) > 0 and np.max(future_highs) > z_high:
                continue

            ts_str = str(data["timestamp"].iloc[i])[:16]
            strength = round(min(99.0, 55.0 + ((-leg_move) / curr_atr) * 12.0 + min(leg_vol_ratio, 3.0) * 6.0), 1)
            supply_zones.append(
                {
                    "timeframe": timeframe,
                    "zone_type": "SUPPLY",
                    "zone_low": round(z_low, 2),
                    "zone_high": round(z_high, 2),
                    "origin_ts": ts_str,
                    "strength": strength,
                    "leg_vol_ratio": round(float(leg_vol_ratio), 2),
                    "avg_vol": float(avg_vol[-1]) if avg_vol[-1] > 0 else 0.0,
                }
            )

        if len(demand_zones) >= max_zones_per_side and len(supply_zones) >= max_zones_per_side:
            break

    return demand_zones[:max_zones_per_side] + supply_zones[:max_zones_per_side]


def evaluate_institutional_footprint(
    ltp: float,
    day_open: float,
    day_high: float,
    day_low: float,
    day_volume: float,
    avg_daily_vol: float,
    tot_buy_qty: float,
    tot_sell_qty: float,
    zone_type: Optional[str] = None,
) -> Dict:
    """
    Calculates real-time Institutional Buying / Selling score from:
    1) Volume Spike vs 20-day average
    2) Order-book Total Buy vs Total Sell Quantity imbalance
    3) Intraday rejection wick / price action
    """
    vol_ratio = round(day_volume / avg_daily_vol, 2) if avg_daily_vol > 0 and day_volume > 0 else 1.0
    buy_sell_ratio = round(tot_buy_qty / max(tot_sell_qty, 1.0), 2) if tot_buy_qty > 0 else 1.0
    sell_buy_ratio = round(tot_sell_qty / max(tot_buy_qty, 1.0), 2) if tot_sell_qty > 0 else 1.0

    candle_range = max(day_high - day_low, 1e-6)
    lower_wick_pct = (min(ltp, day_open) - day_low) / candle_range if day_high > day_low else 0.0
    upper_wick_pct = (day_high - max(ltp, day_open)) / candle_range if day_high > day_low else 0.0

    inst_side = None
    inst_score = 0
    reasons: List[str] = []

    # Check Institutional Buying
    buy_points = 0
    if vol_ratio >= 1.8:
        buy_points += 40
        reasons.append(f"Vol {vol_ratio}x")
    elif vol_ratio >= 1.3:
        buy_points += 20
        reasons.append(f"Vol {vol_ratio}x")

    if buy_sell_ratio >= 1.6:
        buy_points += 35
        reasons.append(f"Buyers {buy_sell_ratio}x")
    elif buy_sell_ratio >= 1.25:
        buy_points += 15

    if lower_wick_pct >= 0.35 or (ltp > day_open and zone_type == "DEMAND"):
        buy_points += 25
        reasons.append("Zone Rejection")

    # Check Institutional Selling
    sell_points = 0
    if vol_ratio >= 1.8:
        sell_points += 40
    elif vol_ratio >= 1.3:
        sell_points += 20

    if sell_buy_ratio >= 1.6:
        sell_points += 35
        reasons.append(f"Sellers {sell_buy_ratio}x")
    elif sell_buy_ratio >= 1.25:
        sell_points += 15

    if upper_wick_pct >= 0.35 or (ltp < day_open and zone_type == "SUPPLY"):
        sell_points += 25
        reasons.append("Supply Rejection")

    if zone_type == "DEMAND" or (zone_type is None and buy_points >= sell_points):
        if buy_points >= 55:
            inst_side = "INST_BUYING"
            inst_score = min(99, buy_points)
    if zone_type == "SUPPLY" or (zone_type is None and sell_points > buy_points):
        if sell_points >= 55:
            inst_side = "INST_SELLING"
            inst_score = min(99, sell_points)

    return {
        "is_institutional": inst_side is not None,
        "inst_side": inst_side,
        "inst_score": inst_score,
        "vol_ratio": vol_ratio,
        "buy_sell_ratio": buy_sell_ratio,
        "sell_buy_ratio": sell_buy_ratio,
        "reasons": reasons[:3],
    }
