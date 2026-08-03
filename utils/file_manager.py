import os
import shutil
from aiogram import Bot

async def download_file(bot: Bot, file_id: str, destination: str):
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, destination)
    return destination

def cleanup_files(*paths):
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path) # stems folder
            else:
                os.remove(path) # source audio