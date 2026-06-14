import os
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client

logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
SESSION_STRING = os.environ.get("SESSION_STRING", "")

print(f"✅ CONFIG: API_ID={API_ID}, OWNER_ID={OWNER_ID}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

def parse_tme_link(text):
    # t.me/c/CHATID/TOPICID/MSGID yoki t.me/c/CHATID/MSGID
    m = re.search(r"https?://t\.me/c/(\d+)/(\d+)(?:/(\d+))?", text)
    if m:
        chat_id = int("-100" + m.group(1))
        msg_id = int(m.group(3)) if m.group(3) else int(m.group(2))
        return chat_id, msg_id
    # t.me/username/MSGID
    m2 = re.search(r"https?://t\.me/([^/c][^/]*)/(\d+)", text)
    if m2:
        return m2.group(1), int(m2.group(2))
    return None, None

def owner(m: Message):
    return m.from_user.id == OWNER_ID

@dp.message(Command("start"))
async def start(message: Message):
    if not owner(message): return
    await message.answer("✅ Bot tayyor!\n\n• Havola → bitta media\n• /topic [havola] → topic\n• /status\n• /dialogs — guruhlar ro'yxati")

@dp.message(Command("status"))
async def status(message: Message):
    if not owner(message): return
    try:
        me = await user.get_me()
        await message.answer(f"✅ {me.first_name} ({me.phone_number})")
    except Exception as e:
        await message.answer(f"❌ {e}")

@dp.message(Command("dialogs"))
async def dialogs(message: Message):
    if not owner(message): return
    proc = await message.answer("🔍 Guruhlar yuklanmoqda...")
    try:
        lines = []
        async for dialog in user.get_dialogs():
            chat = dialog.chat
            if chat.type.name in ("GROUP", "SUPERGROUP", "CHANNEL"):
                lines.append(f"• {chat.title} | `{chat.id}`")
            if len(lines) >= 30:
                break
        await proc.edit_text("📋 Guruhlar:\n\n" + "\n".join(lines))
    except Exception as e:
        await proc.edit_text(f"❌ {e}")

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
            ids_str = ",".join(map(str, media_msgs))
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha", callback_data=f"y|{chat_id}|{ids_str}"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="n"),
            ]])
            await proc.edit_text(f"⚠️ {count} ta media. Yuborilsinmi?", reply_markup=kb)
    except Exception as e:
        await proc.edit_text(f"❌ {e}")

async def send_media(to_chat, from_chat, ids, status_msg):
    sent = 0
    for mid in ids:
        try:
            await user.copy_message(chat_id=to_chat, from_chat_id=from_chat, message_id=mid)
            sent += 1
            await asyncio.sleep(0.5)
        except:
            pass
    await status_msg.edit_text(f"✅ {sent}/{len(ids)} yuborildi.")

@dp.callback_query()
async def cb(cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID: return
    if cq.data == "n":
        await cq.message.edit_text("❌ Bekor.")
    elif cq.data.startswith("y|"):
        _, chat_id, ids_str = cq.data.split("|", 2)
        ids = list(map(int, ids_str.split(",")))
        await cq.message.edit_text("📦 Yuborilmoqda...")
        await send_media(cq.message.chat.id, int(chat_id), ids, cq.message)
    await cq.answer()

@dp.message(F.text)
async def handle_text(message: Message):
    if not owner(message): return
    text = message.text.strip()
    chat_id, msg_id = parse_tme_link(text)
    if not chat_id:
        await message.answer("❓ Havola yuboring yoki /topic [havola]")
        return
    proc = await message.answer(f"⏳ Olinmoqda...\n`chat_id={chat_id}`", parse_mode="markdown")
    try:
        msg = await user.get_messages(chat_id, msg_id)
        if msg.empty:
            await proc.edit_text("❌ Xabar topilmadi.")
            return
        await user.copy_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=msg_id)
        await proc.delete()
    except Exception as e:
        await proc.edit_text(f"❌ {e}")

async def main():
    await user.start()
    me = await user.get_me()
    print(f"✅ User: {me.first_name} ({me.phone_number})")
    print("🤖 Polling boshlandi...")
    await dp.start_polling(bot)

asyncio.run(main())
