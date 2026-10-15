import logging
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import ADMIN_ID
from db import users_col, next_seq
from helpers import now_utc, today_str, main_kb, admin_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(msg: Message):
    uid      = msg.from_user.id
    name     = msg.from_user.first_name or "User"
    username = msg.from_user.username or "-"
    is_admin = (uid == ADMIN_ID)

    existing = users_col.find_one({"_id": uid}, {"id": 1})

    if existing:
        users_col.update_one(
            {"_id": uid},
            {"$set": {"name": name, "last_active": now_utc(), "blocked": False}},
        )
    else:
        new_id = next_seq("user_seq")
        users_col.insert_one({
            "_id": uid,
            "id": new_id,
            "name": name,
            "username": username,
            "blocked": False,
            "processing": False,
            "views": {
                "last_video": None,
                "history": [],
                "deleted_ids": [],
            },
            "stats": {"today": 0, "total": 0, "bonus_date": None},
            "last_active": now_utc(),
            "date": today_str(),
        })
        logging.info(f"New user id={new_id} uid={uid}")

        # notify admin only about real users (not himself)
        if not is_admin:
            try:
                await msg.bot.send_message(
                    ADMIN_ID,
                    f"🆕 <b>New User</b>\n\n"
                    f"Name: <b>{name}</b>\n"
                    f"Username: @{username}\n"
                    f"UID: <code>{uid}</code>\n"
                    f"User#: <b>{new_id}</b>",
                )
            except Exception as e:
                logging.warning(f"admin notify failed: {e}")

    kb = admin_kb() if is_admin else main_kb()

    await msg.answer(
        f"👋 <b>স্বাগতম {name}!</b>\n\n"
        f"নতুন ভিডিও পেতে নিচের বাটনে ক্লিক করুন।",
        reply_markup=kb,
    )