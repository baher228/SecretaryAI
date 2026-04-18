import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_TELEGRAM_ID = int(os.environ["OWNER_TELEGRAM_ID"])
ZAI_API_KEY = os.environ["ZAI_API_KEY"]
ZAI_BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
ZAI_MODEL = os.environ.get("ZAI_MODEL", "glm-5.1")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/secretary.db")
