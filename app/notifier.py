import threading

import requests
from logzero import logger

from . import config


def _send(text: str) -> None:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)


def alert_touch(hit: dict) -> None:
    icon = "🟢" if hit["side"] == "DEMAND" else "🔴"
    text = (
        f"{icon} <b>{hit['symbol']}</b> touched 1D {hit['side']} zone\n"
        f"LTP: {hit['ltp']:.2f}  |  Day H/L: {hit['high']:.2f} / {hit['low']:.2f}\n"
        f"Zone: {hit['proximal']:.2f} – {hit['distal']:.2f}  ({hit['pattern']}, {hit['freshness']})\n"
        f"Time: {hit['time']}"
    )
    threading.Thread(target=_send, args=(text,), daemon=True).start()
