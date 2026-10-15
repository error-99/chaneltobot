import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from db import init_db
from handlers import register_all
from helpers import set_bot_username

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

register_all(dp)


async def main():
    init_db()
    logging.info("Bot starting...")
    me = await bot.get_me()
    set_bot_username(me.username)
    logging.info(f"Bot: @{me.username} ({me.id})")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())