import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

GET_VIDEO_TEXT = "🎬 Get Video"

# ---- Admin reply-keyboard labels ----
ADMIN_STATUS_TEXT = "📊 Status"
ADMIN_USERS_TEXT  = "👥 Users"

CHANNELS_FILE = Path(__file__).parent / "channels.json"

# ---- Bot username (set by bot.py at startup) ----
BOT_USERNAME = ""


def set_bot_username(username: str):
    global BOT_USERNAME
    BOT_USERNAME = username or ""
    logging.info(f"Bot username cached: @{BOT_USERNAME}")


# ---------- Channels JSON ----------
def _load_channels_cfg() -> dict:
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "channels":    data.get("channels", []) or [],
            "bonus_limit": int(data.get("bonus_limit", 0)),
        }
    except FileNotFoundError:
        logging.warning(f"{CHANNELS_FILE} not found — force-join disabled")
        return {"channels": [], "bonus_limit": 0}
    except Exception as e:
        logging.warning(f"channels.json load failed: {e}")
        return {"channels": [], "bonus_limit": 0}


def get_force_channels() -> list:
    return _load_channels_cfg()["channels"]


def get_bonus_limit() -> int:
    return _load_channels_cfg()["bonus_limit"]


# ---------- Time helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------- Keyboards ----------
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=GET_VIDEO_TEXT)]],
        resize_keyboard=True,
        is_persistent=False,
    )


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ADMIN_STATUS_TEXT),
             KeyboardButton(text=ADMIN_USERS_TEXT)],
            [KeyboardButton(text=GET_VIDEO_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


async def get_not_joined(bot, user_id: int) -> list:
    channels = get_force_channels()
    if not channels:
        return []
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception as e:
            logging.warning(f"force_join check {ch['chat_id']}: {e}")
            not_joined.append(ch)
    return not_joined


def force_join_kb(not_joined: list) -> InlineKeyboardMarkup:
    rows = []

    # Real channels/groups (must actually join)
    for ch in not_joined:
        # "type" field in channels.json — "group" or "channel" (default)
        kind = (ch.get("type") or "channel").lower()
        icon = "👥" if kind == "group" else "📢"
        label = "Group" if kind == "group" else "Channel"
        rows.append([InlineKeyboardButton(
            text=f"{icon} Join {label}: {ch['name']}",
            url=ch["url"],
        )])

    # Fake-mandatory Share button — NOT verified on ✅ I Joined
    if BOT_USERNAME:
        share_text = "🔥 Best video bot! Get fresh videos:"
        share_url = (
            f"https://t.me/share/url"
            f"?url=https://t.me/{BOT_USERNAME}"
            f"&text={quote(share_text)}"
        )
        rows.append([InlineKeyboardButton(
            text="🚀 Share Bot (Required)",
            url=share_url,
        )])

    rows.append([InlineKeyboardButton(
        text="✅ I Joined",
        callback_data="fj_check",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)
