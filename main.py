import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers.base import router as base_router
from handlers.audio import router as audio_router
from handlers.admin import router as admin_router

async def main():
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(base_router)
    dp.include_router(audio_router)
    dp.include_router(admin_router)

    logging.info("bot started")
    
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stop")