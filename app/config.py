import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "scanner.db"
STATIC_DIR = BASE_DIR / "static"
FNO_FALLBACK_FILE = BASE_DIR / "fno_stocks.json"
SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip().strip('"').strip("'")
    if value.lower().startswith("your_") or value.lower() in {"xxx", "changeme"}:
        return ""
    return value


ANGEL_API_KEY = _env("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = _env("ANGEL_CLIENT_CODE")
ANGEL_PIN = _env("ANGEL_PIN")
ANGEL_TOTP_SECRET = _env("ANGEL_TOTP_SECRET").replace(" ", "")
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
SCAN_INTERVAL_SEC = max(5, int(_env("SCAN_INTERVAL_SEC", "10") or "10"))


def angel_configured() -> bool:
    return all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET])
