import asyncio
import logging

from aiogram import Router
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ForceReply,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from config import ADMIN_ID
from db import users_col
from .users import _safe_edit
from .status import admin_home_text, admin_home_kb

router = Router()


# ============================================================
#  Pending broadcast buffer (per-admin, in-memory)
#  Admin replies to the ForceReply prompt → this stores the msg
# ============================================================
PENDING_BROADCAST = {}   # {admin_id: {"from_chat_id":..., "message_id":...}}


# ============================================================
#  🧹 Clean blocked users
# ============================================================
@router.callback_query(lambda c: c.data == "adm_clean")
async def adm_clean_confirm(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, clean now", callback_data="adm_clean_yes")],
        [InlineKeyboardButton(text="❌ Cancel",        callback_data="adm_home")],
    ])
    await _safe_edit(
        cb,
        "🧹 <b>Clean Blocked Users</b>\n\n"
        "This will ping every user with a tiny typing action.\n"
        "Users who blocked the bot will be <b>deleted from the database</b>.\n\n"
        "⚠️ Cannot be undone. Continue?",
        kb,
    )


@router.callback_query(lambda c: c.data == "adm_clean_yes")
async def adm_clean_run(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    await cb.answer("Scanning…")

    checked   = 0
    blocked   = 0
    deleted   = 0
    failed    = 0
    skipped   = 0
    admin_uid = ADMIN_ID

    cursor = users_col.find({}, {"_id": 1})

    for u in cursor:
        uid = u["_id"]
        if uid == admin_uid:
            skipped += 1
            continue
        checked += 1
        try:
            # sendChatAction is cheap and raises Forbidden if blocked
            await cb.bot.send_chat_action(uid, "typing")
        except TelegramForbiddenError:
            blocked += 1
            # delete from DB
            try:
                users_col.delete_one({"_id": uid})
                deleted += 1
                logging.info(f"clean: deleted blocked user {uid}")
            except Exception as e:
                failed += 1
                logging.warning(f"clean delete failed {uid}: {e}")
        except TelegramRetryAfter as e:
            # rate limited — sleep and retry once
            await asyncio.sleep(e.retry_after + 1)
            try:
                await cb.bot.send_chat_action(uid, "typing")
            except TelegramForbiddenError:
                blocked += 1
                try:
                    users_col.delete_one({"_id": uid})
                    deleted += 1
                except Exception:
                    failed += 1
        except Exception as e:
            logging.warning(f"clean check failed {uid}: {e}")
            failed += 1

        # gentle rate-limit: 20 msgs/sec max
        await asyncio.sleep(0.05)

    await _safe_edit(
        cb,
        f"🧹 <b>Clean Complete</b>\n\n"
        f"🔍 Checked: <b>{checked}</b>\n"
        f"🚫 Blocked detected: <b>{blocked}</b>\n"
        f"🗑 Deleted from DB: <b>{deleted}</b>\n"
        f"⚠️ Errors: <b>{failed}</b>\n"
        f"⏭ Skipped (admin): <b>{skipped}</b>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Home", callback_data="adm_home")]
        ]),
    )


# ============================================================
#  📢 Broadcast
# ============================================================
@router.callback_query(lambda c: c.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    await _safe_edit(
        cb,
        "📢 <b>Broadcast</b>\n\n"
        "Reply to this message with the content to broadcast.\n"
        "You can send:\n"
        "• Text\n"
        "• Photo with caption\n"
        "• Video with caption\n"
        "• Document\n"
        "• Sticker\n\n"
        "I'll copy your reply as-is to every user.",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="adm_home")]
        ]),
    )

    # Ask the admin to reply with the broadcast content
    await cb.message.answer(
        "📝 <b>Reply with the broadcast content</b> to this message.",
        reply_markup=ForceReply(selective=True, input_field_placeholder="Type your broadcast…"),
    )


# Handle admin's reply → capture content
@router.message(lambda m: m.from_user.id == ADMIN_ID
                         and m.reply_to_message is not None
                         and m.reply_to_message.text is not None
                         and "Reply with the broadcast content" in (m.reply_to_message.text or ""))
async def adm_broadcast_capture(msg: Message):
    PENDING_BROADCAST[ADMIN_ID] = {
        "from_chat_id": msg.chat.id,
        "message_id":   msg.message_id,
    }
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Send to ALL users", callback_data="adm_broadcast_go")],
        [InlineKeyboardButton(text="❌ Cancel",            callback_data="adm_broadcast_cancel")],
    ])
    await msg.answer(
        "✅ Content captured.\n\n"
        "Ready to send to <b>all users</b>?\n\n"
        "This may take a while. Progress will be reported at the end.",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data == "adm_broadcast_cancel")
async def adm_broadcast_cancel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    PENDING_BROADCAST.pop(ADMIN_ID, None)
    await _safe_edit(cb, "❌ Broadcast cancelled.",
                     InlineKeyboardMarkup(inline_keyboard=[
                         [InlineKeyboardButton(text="🔙 Home", callback_data="adm_home")]
                     ]))


@router.callback_query(lambda c: c.data == "adm_broadcast_go")
async def adm_broadcast_go(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    pending = PENDING_BROADCAST.pop(ADMIN_ID, None)
    if not pending:
        await cb.answer("Nothing to broadcast", show_alert=True)
        return

    await cb.answer("Broadcasting…")
    await _safe_edit(
        cb,
        "🚀 <b>Broadcasting…</b>\n\nThis may take a few minutes. Please wait.",
        None,
    )

    sent    = 0
    failed  = 0
    blocked = 0
    deleted = 0
    total   = 0

    cursor = users_col.find({}, {"_id": 1})
    for u in cursor:
        uid = u["_id"]
        if uid == ADMIN_ID:
            continue
        total += 1
        try:
            await cb.bot.copy_message(
                chat_id=uid,
                from_chat_id=pending["from_chat_id"],
                message_id=pending["message_id"],
                protect_content=True,
            )
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await cb.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=pending["from_chat_id"],
                    message_id=pending["message_id"],
                    protect_content=True,
                )
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
                try:
                    users_col.delete_one({"_id": uid})
                    deleted += 1
                except Exception:
                    pass
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            blocked += 1
            try:
                users_col.delete_one({"_id": uid})
                deleted += 1
            except Exception:
                pass
        except Exception as e:
            logging.warning(f"broadcast send failed {uid}: {e}")
            failed += 1

        # 25 msgs/sec safety
        await asyncio.sleep(0.04)

    await _safe_edit(
        cb,
        f"📢 <b>Broadcast complete</b>\n\n"
        f"👥 Total tried: <b>{total}</b>\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"🚫 Blocked: <b>{blocked}</b>\n"
        f"🗑 Deleted from DB: <b>{deleted}</b>\n"
        f"⚠️ Failed: <b>{failed}</b>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Home", callback_data="adm_home")]
        ]),
    )
