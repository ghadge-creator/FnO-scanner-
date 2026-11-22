import os
import requests


def send_alert(title: str, body: str) -> None:
    """
    Sends optional Telegram notification if TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID are set.
    Browser push & sound alerts work automatically via /api/state polling.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        return
    try:
        url = f"https://telegram.org{bot_token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": f"🚨 {title}\n{body}"}, timeout=5)
    except Exception:
        pass
