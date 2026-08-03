import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

admin_ids_str = os.getenv("ADMIN_ID", "")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip()]

DUMP_CHAT_ID = int(os.getenv("DUMP_CHAT_ID", 0))

if not BOT_TOKEN:
    raise ValueError("no token in .env")