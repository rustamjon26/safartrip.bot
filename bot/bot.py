from pyrogram import Client, filters

# Import centralized config from project root
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import get_pyrogram_config  # noqa: E402

cfg = get_pyrogram_config()

app = Client(
    "admin_bot",
    api_id=cfg["api_id"],
    api_hash=cfg["api_hash"],
    bot_token=cfg["bot_token"],
)


@app.on_message(filters.command("start"))
def start(client, message):
    message.reply("🤖 Admin bot ishga tushdi!")


@app.on_message(filters.command("test"))
def test(client, message):
    message.reply("✅ Hammasi joyida!")


if __name__ == "__main__":
    print("Admin bot ishga tushmoqda...")
    app.run()
