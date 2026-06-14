import os
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
SESSION_STRING = os.environ.get("SESSION_STRING", "")

print(f"✅ CONFIG: API_ID={API_ID}, OWNER_ID={OWNER_ID}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Session string orqali ulanamiz
user = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

def parse_tme_link(text):
    pattern = r"https?://t\.me/(c/(\d+)|([^/]+))/(\d+)"
    match = re.search(pattern, text)
    if not match:
        return None, None
    chat_id = int("-100" + match.group(2)) if match.group(2) else match.group(3)
    return chat_id, int(match.group(4))

def owner(message: Message) -> bool:
    return message.from_user.id == OWNER_ID

@dp.message(Command("start"))
async def start(message: Message):
    if not owner(message): return
    await message.answer("✅ Bot tayyor!\n\n• Havola → bitta media\n• /topic [havola] → topic ichidagi barchasi\n• /status")

@dp.message(Command("status"))
async def status(message: Message):
    if not owner(message): return
    try:
        me = await user.get_me()
        await message.answer(f"✅ Ulangan: {me.first_name} ({me.phone_number})")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("topic"))
async def topic_cmd(message: Message):
    if not owner(message): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❗ /topic https://t.me/c/1234567890/456")
        return
    chat_id, thread_id = parse_tme_link(args[1])
    if not chat_id:
        await message.answer("❌ Havola xato.")
        return
    proc = await message.answer("🔍 Tekshirilmoqda...")
    try:
        media_msgs = []
        async for msg in user.get_chat_history(chat_id, limit=1000):
            if (msg.reply_to_message_id == thread_id or msg.id == thread_id) and msg.media:
                media_msgs.append(msg.id)
        media_msgs.sort()
        if not media_msgs:
            await proc.edit_text("❌ Media topilmadi.")
            return
        count = len(media_msgs)
        if count <= 50:
            await proc.edit_text(f"📦 {count} ta yuborilmoqda...")
            await send_media(message.chat.id, chat_id, media_msgs, proc)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha", callback_data=f"yes_{chat_id}_{','.join(map(str,media_msgs))}"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="no"),
            ]])
            await proc.edit_text(f"⚠️ {count} ta media bor. Yuborilsinmi?", reply_markup=kb)
    except Exception as e:
        await proc.edit_text(f"❌ {e}")

async def send_media(to_chat_id, from_chat_id, media_msgs, status_msg):
    sent = 0
    for msg_id in media_msgs:
        try:
            await user.copy_message(chat_id=to_chat_id, from_chat_id=from_chat_id, message_id=msg_id)
            sent += 1
            await asyncio.sleep(0.5)
        except:
            pass
    await status_msg.edit_text(f"✅ {sent}/{len(media_msgs)} yuborildi.")

@dp.callback_query()
async def cb(cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID: return
    if cq.data == "no":
        await cq.message.edit_text("❌ Bekor.")
    elif cq.data.startswith("yes_"):
        parts = cq.data.split("_", 2)
        chat_id = int(parts[1])
        media_msgs = list(map(int, parts[2].split(",")))
        await cq.message.edit_text("📦 Yuborilmoqda...")
        await send_media(cq.message.chat.id, chat_id, media_msgs, cq.message)
    await cq.answer()

@dp.message(F.text)
async def handle_text(message: Message):
    if not owner(message): return
    text = message.text.strip()

    chat_id, msg_id = parse_tme_link(text)
    if not chat_id:
        await message.answer("❓ Havola yuboring yoki /topic [havola]")
        return
    proc = await message.answer("⏳ Olinmoqda...")
    try:
        msg = await user.get_messages(chat_id, msg_id)
        if msg.empty:
            await proc.edit_text("❌ Topilmadi.")
            return
        await user.copy_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=msg_id)
        await proc.delete()
    except Exception as e:
        await proc.edit_text(f"❌ {e}")

async def main():
    await user.start()
    me = await user.get_me()
    print(f"✅ User ulandi: {me.first_name}")
    print("🤖 Bot polling boshlandi...")
    await dp.start_polling(bot)

asyncio.run(main())
