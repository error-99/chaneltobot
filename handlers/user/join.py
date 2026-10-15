from aiogram import Router, F
from aiogram.types import CallbackQuery

from db import users_col
from helpers import today_str, get_not_joined, get_bonus_limit

router = Router()


@router.callback_query(F.data == "fj_check")
async def on_fj_check(cb: CallbackQuery):
    uid   = cb.from_user.id
    today = today_str()

    user = users_col.find_one({"_id": uid})
    if not user:
        await cb.answer("আবার /start দিন", show_alert=True)
        return

    not_joined = await get_not_joined(cb.bot, uid)
    if not_joined:
        await cb.answer(
            f"❌ এখনো {len(not_joined)}টি চ্যানেল জয়েন করেননি!",
            show_alert=True,
        )
        return

    # user has joined everything — grant today's bonus
    if user.get("stats", {}).get("bonus_date") != today:
        users_col.update_one(
            {"_id": uid},
            {"$set": {"stats.bonus_date": today}},
        )
        bonus = get_bonus_limit()
        try:
            await cb.message.edit_text(
                f"🎉 ধন্যবাদ! আপনি <b>+{bonus} ভিডিও</b> বোনাস পেয়েছেন।\n\n"
                f"এখন 🎬 <b>Get Video</b> ক্লিক করুন।",
            )
        except Exception:
            pass
        await cb.answer("✅ বোনাস অ্যাক্টিভ!")
    else:
        try:
            await cb.message.edit_text("✅ সব চ্যানেল জয়েন করা আছে। Get Video চাপুন।")
        except Exception:
            pass
        await cb.answer("✅ Already joined")