import logging
from datetime import timezone, timedelta

from aiogram import Router, F
from aiogram.types import Message
from pymongo import ASCENDING

from config import (
    MODE, CATEGORY, COOLDOWN_SECONDS, DAILY_LIMIT,
    ADMIN_ID,
)
from db import users_col, videos_col, COUNTER_ID
from helpers import (
    now_utc, today_str, GET_VIDEO_TEXT,
    get_not_joined, force_join_kb,
    get_force_channels, get_bonus_limit,
)

router = Router()

# ---- Auto-cleanup: delete forwarded messages older than this from user chat
AUTO_DELETE_AFTER_HOURS = 24
AUTO_DELETE_CUTOFF = timedelta(hours=AUTO_DELETE_AFTER_HOURS)


async def auto_cleanup_old_history(bot, uid: int, history: list) -> list:
    """
    Delete any history entry whose `at` is older than AUTO_DELETE_AFTER_HOURS
    from the user's chat. Returns the kept (fresh) entries.
    Also updates DB: rewrites views.history to the kept list.
    """
    if not history:
        return []

    cutoff = now_utc() - AUTO_DELETE_CUTOFF
    kept = []
    deleted_any = False

    for entry in history:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue

        at = entry.get("at")
        # normalize tz
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)

        # if we can't parse, keep it (safer than losing data)
        if at is None:
            kept.append(entry)
            continue

        if at < cutoff:
            smid = entry.get("sent_message_id")
            if smid:
                try:
                    await bot.delete_message(uid, smid)
                    deleted_any = True
                except Exception as e:
                    # already gone / too old / no perms — just drop it
                    logging.info(f"auto-cleanup skip {uid}/{smid}: {e}")
            # drop from kept either way
        else:
            kept.append(entry)

    if deleted_any or len(kept) != len(history):
        try:
            users_col.update_one(
                {"_id": uid},
                {"$set": {"views.history": kept}},
            )
        except Exception as e:
            logging.warning(f"auto-cleanup db update failed: {e}")

    return kept


@router.message(F.text == GET_VIDEO_TEXT)
async def on_get_video(msg: Message):
    uid  = msg.from_user.id
    chat = msg.chat.id
    is_admin = (uid == ADMIN_ID)

    user = users_col.find_one({"_id": uid})

    # regular users must have started the bot
    if not user and not is_admin:
        await msg.answer("আবার /start দিন")
        return

    if user and user.get("blocked"):
        await msg.answer("⛔ ব্লকড")
        return

    if user and user.get("processing"):
        await msg.answer("⏳ একটু অপেক্ষা করুন")
        return

    if user:
        users_col.update_one({"_id": uid}, {"$set": {"processing": True}})

    try:
        today = today_str()

        if user:
            # ---------- daily reset ----------
            if user.get("date") != today:
                users_col.update_one(
                    {"_id": uid},
                    {"$set": {"stats.today": 0, "date": today}},
                )
                user.setdefault("stats", {})["today"] = 0

            # ---------- cooldown (admin skips) ----------
            if not is_admin and COOLDOWN_SECONDS > 0:
                last = user.get("last_active")
                if last:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now_utc() - last).total_seconds()
                    if elapsed < COOLDOWN_SECONDS:
                        wait = int(COOLDOWN_SECONDS - elapsed)
                        await msg.answer(f"⏱ {wait}s পর চেষ্টা করুন")
                        return

            # ---------- AUTO-CLEANUP: remove old forwarded msgs ----------
            raw_hist = user.get("views", {}).get("history", []) or []
            kept_hist = await auto_cleanup_old_history(msg.bot, uid, raw_hist)
            # refresh user object so downstream logic sees fresh list
            user.setdefault("views", {})["history"] = kept_hist

            # ============================================================
            #  DAILY LIMIT — force-join prompt ONLY appears here
            # ============================================================
            if not is_admin and DAILY_LIMIT > 0:
                stats = user.get("stats", {})
                bonus = get_bonus_limit() if stats.get("bonus_date") == today else 0
                effective_limit = DAILY_LIMIT + bonus

                if stats.get("today", 0) >= effective_limit:
                    force_channels = get_force_channels()

                    if bonus > 0 or not force_channels:
                        await msg.answer("📵 আজকের লিমিট শেষ!")
                        return

                    not_joined = await get_not_joined(msg.bot, uid)
                    if not_joined:
                        await msg.answer(
                            f"📵 <b>আজকের লিমিট শেষ!</b>\n\n"
                            f"নিচের সব চ্যানেল জয়েন করলে "
                            f"<b>+{get_bonus_limit()} ভিডিও</b> বোনাস পাবেন:",
                            reply_markup=force_join_kb(not_joined),
                        )
                        return

                    users_col.update_one(
                        {"_id": uid},
                        {"$set": {"stats.bonus_date": today}},
                    )
                    user.setdefault("stats", {})["bonus_date"] = today

        # ---------- exclude list (uses fresh kept history) ----------
        history_raw = user.get("views", {}).get("history", []) if user else []
        history_ids = [
            h.get("video_id") if isinstance(h, dict) else h
            for h in (history_raw or [])
        ]
        history_ids = [x for x in history_ids if x is not None]
        deleted = user.get("views", {}).get("deleted_ids", []) if user else []
        exclude = list(set(history_ids + (deleted or [])))

        # ---------- query ----------
        query = {
            "_id": {"$ne": COUNTER_ID},
            "message_id": {"$nin": exclude},
        }
        if CATEGORY:
            query["category"] = CATEGORY

        # ---------- pick ----------
        if MODE == "random":
            docs = list(videos_col.aggregate([
                {"$match": query},
                {"$sample": {"size": 1}},
            ]))
            video = docs[0] if docs else None
        else:
            video = videos_col.find_one(
                query,
                sort=[("created_at", ASCENDING), ("id", ASCENDING)],
            )

        if not video:
            await msg.bot.send_message(chat, "📭 <b>সব ভিডিও দেখা হয়ে গেছে!</b>")
            return

        channel_id = int(video["channel_id"])
        video_msg  = int(video["message_id"])

        # ---------- forward ----------
        try:
            sent = await msg.bot.forward_message(
                chat_id=chat,
                from_chat_id=channel_id,
                message_id=video_msg,
            )
        except Exception as e:
            logging.warning(f"forward failed: {e}")
            if user:
                users_col.update_one(
                    {"_id": uid},
                    {
                        "$pull": {"views.history": {"video_id": video_msg}},
                        "$addToSet": {"views.deleted_ids": video_msg},
                    },
                )
            await msg.bot.send_message(chat, "⚠️ এই ভিডিওটি আর নেই।")
            return

        # ---------- update user (skip stats for admin) ----------
        if user and not is_admin:
            users_col.update_one(
                {"_id": uid},
                {
                    "$set": {
                        "views.last_video": video_msg,
                        "last_active": now_utc(),
                    },
                    "$push": {
                        "views.history": {
                            "video_id": video_msg,
                            "sent_message_id": sent.message_id,
                            "at": now_utc(),
                        }
                    },
                    "$inc": {"stats.today": 1, "stats.total": 1},
                },
            )
        elif user and is_admin:
            users_col.update_one(
                {"_id": uid},
                {"$set": {"last_active": now_utc()}},
            )

    except Exception as e:
        logging.exception(f"get_video error: {e}")
        await msg.answer("❌ সমস্যা হয়েছে")

    finally:
        if user:
            users_col.update_one({"_id": uid}, {"$set": {"processing": False}})