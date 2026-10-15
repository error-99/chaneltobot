import os
from urllib.parse import quote_plus
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    # python-dotenv not installed — fall back to os.environ only
    pass


# ============================================================
#  SECRETS  (put in .env — NEVER commit .env to git)
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

# ---- Mongo parts (safer: no manual URL-encoding needed) ----
MONGO_USER = os.getenv("MONGO_USER", "mo8022_bachelor")
MONGO_PASS = os.getenv("MONGO_PASS", "Sha@bbir..1")     # raw password, no encoding
MONGO_HOST = os.getenv("MONGO_HOST", "mongo2.serv00.com")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB   = os.getenv("MONGO_DB",   "mo8022_bachelor")
MONGO_AUTH_SOURCE = os.getenv("MONGO_AUTH_SOURCE", MONGO_DB)

# ---- Build URI with proper URL-encoding of user & password ----
MONGO_URI = (
    f"mongodb://{quote_plus(MONGO_USER)}:{quote_plus(MONGO_PASS)}"
    f"@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}"
    f"?authSource={MONGO_AUTH_SOURCE}"
)


# ============================================================
#  BOT BEHAVIOR
# ============================================================
MODE             = "random"     # "random" | "sequential"
CATEGORY         = None         # e.g. "funny" — filter videos by category
COOLDOWN_SECONDS = 0            # seconds between two video requests
DAILY_LIMIT      = 5            # normal daily video limit (0 = unlimited)


# ============================================================
#  ADMIN
# ============================================================
ADMIN_ID = int(os.getenv("ADMIN_ID", "5087403859"))