import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

_allowed_raw = os.environ.get("ALLOWED_TELEGRAM_IDS", "")
_owner_fallback = os.environ.get("OWNER_TELEGRAM_ID", "")

if _allowed_raw.strip():
    ALLOWED_TELEGRAM_IDS = [int(x.strip()) for x in _allowed_raw.split(",") if x.strip()]
elif _owner_fallback.strip():
    ALLOWED_TELEGRAM_IDS = [int(_owner_fallback.strip())]
else:
    raise RuntimeError("Set ALLOWED_TELEGRAM_IDS or OWNER_TELEGRAM_ID in .env")

OWNER_TELEGRAM_ID = ALLOWED_TELEGRAM_IDS[0]
ZAI_API_KEY = os.environ["ZAI_API_KEY"]
ZAI_BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
ZAI_MODEL = os.environ.get("ZAI_MODEL", "glm-5.1")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/secretary.db")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "./data/service_account.json")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
