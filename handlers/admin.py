from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from config import ADMIN_IDS
from utils.stats_manager import get_stats

router = Router()

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    s = get_stats()
    if s:
        text = (
            "stats:\n\n"
            f"total processed: {s['total_processed']}\n"
            f"full stems: {s['full_stems']}\n"
            f"fast modes: {s['fast_modes']}"
        )
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("stats is empty")
