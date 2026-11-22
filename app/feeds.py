"""yfinance (.NS) fallback data source."""
import pandas as pd
from logzero import logger


def _pick(df, ticker):
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(0):
            return df[ticker]
        return None
    return df


def yf_history(stocks: list) -> dict:
    import yfinance as yf

    out = {}
    for i in range(0, len(stocks), 40):
        chunk = stocks[i : i + 40]
        tks = [s["yf"] for s in chunk]
        try:
            df = yf.download(
                tks, period="1y", interval="1d", group_by="ticker",
                auto_adjust=False, progress=False, threads=True,
            )
        except Exception as e:
            logger.warning("yfinance history chunk failed: %s", e)
            continue
        for s in chunk:
            try:
                d = _pick(df, s["yf"])
                if d is None:
                    continue
                d = d.dropna(subset=["Open", "High", "Low", "Close"])
                rows = [
                    (idx.strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]),
                     float(r["Low"]), float(r["Close"]))
                    for idx, r in d.iterrows()
                ]
                if rows:
                    out[s["symbol"]] = rows
            except Exception as e:
                logger.warning("yfinance parse failed for %s: %s", s["symbol"], e)
    return out


def yf_quotes(stocks: list) -> dict:
    import yfinance as yf

    out = {}
    for i in range(0, len(stocks), 60):
        chunk = stocks[i : i + 60]
        tks = [s["yf"] for s in chunk]
        try:
            df = yf.download(
                tks, period="5d", interval="1d", group_by="ticker",
                auto_adjust=False, progress=False, threads=True,
            )
        except Exception as e:
            logger.warning("yfinance quote chunk failed: %s", e)
            continue
        for s in chunk:
            try:
                d = _pick(df, s["yf"])
                if d is None:
                    continue
                d = d.dropna(subset=["Close"])
                if d.empty:
                    continue
                last = d.iloc[-1]
                out[s["symbol"]] = {
                    "ltp": float(last["Close"]),
                    "open": float(last["Open"]),
                    "high": float(last["High"]),
                    "low": float(last["Low"]),
                }
            except Exception:
                continue
    return out
