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
SESSION_NAME = "user_session"

print(f"✅ CONFIG: API_ID={API_ID}, OWNER_ID={OWNER_ID}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

login_state = {}
pending_topics = {}

def parse_tme_link(text):
    pattern = r"https?://t\.me/(c/(\d+)|([^/]+))/(\d+)"
    match = re.search(pattern, text)
    if not match:
        return None, None
    chat_id = int("-100" + match.group(2)) if match.group(2) else match.group(3)
    return chat_id, int(match.group(4))

def owner(message: Message) -> bool:
    return message.from_user.id == OWNER_ID

# ── /start ──
@dp.message(Command("start"))
async def start(message: Message):
    print(f"📩 /start: {message.from_user.id}")
    if not owner(message): return
    if await user.is_connected():
        await message.answer("✅ Ulangan.\n\n• Havola → bitta media\n• /topic [havola] → topic ichidagi barchasi\n• /status\n• /logout")
    else:
        await message.answer("👋 /login yozing.")

# ── /status ──
@dp.message(Command("status"))
async def status(message: Message):
    if not owner(message): return
    if await user.is_connected():
        me = await user.get_me()
        await message.answer(f"✅ {me.first_name} ({me.phone_number})")
    else:
        await message.answer("❌ Ulanmagan. /login")

# ── /login ──
@dp.message(Command("login"))
async def login_start(message: Message):
    if not owner(message): return
    if await user.is_connected():
        await message.answer("✅ Allaqachon ulangansiz.")
        return
    login_state[message.from_user.id] = {"step": "phone"}
    await message.answer("📱 Telefon raqamingizni yuboring:\nMasalan: +998901234567")

# ── /logout ──
@dp.message(Command("logout"))
async def logout(message: Message):
    if not owner(message): return
    if await user.is_connected():
        await user.stop()
        if os.path.exists(f"{SESSION_NAME}.session"):
            os.remove(f"{SESSION_NAME}.session")
        await message.answer("🔓 Chiqdingiz.")
    else:
        await message.answer("Ulanmagan.")

# ── /topic ──
@dp.message(Command("topic"))
async def topic_cmd(message: Message):
    if not owner(message): return
    if not await user.is_connected():
        await message.answer("❌ /login yozing.")
        return
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
            pending_topics[message.from_user.id] = {"chat_id": chat_id, "media_msgs": media_msgs}
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha", callback_data="topic_yes"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="topic_no"),
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

# ── Callback ──
@dp.callback_query(F.data.in_({"topic_yes", "topic_no"}))
async def cb(cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID:
        return
    if cq.data == "topic_no":
        pending_topics.pop(cq.from_user.id, None)
        await cq.message.edit_text("❌ Bekor.")
    elif cq.data == "topic_yes":
        p = pending_topics.pop(cq.from_user.id, None)
        if not p:
            await cq.message.edit_text("❌ Topilmadi.")
            return
        await cq.message.edit_text("📦 Yuborilmoqda...")
        await send_media(cq.message.chat.id, p["chat_id"], p["media_msgs"], cq.message)
    await cq.answer()

# ── Matn xabarlar (login + link) ──
@dp.message(F.text)
async def handle_text(message: Message):
    if not owner(message): return
    text = message.text.strip()
    uid = message.from_user.id
    state = login_state.get(uid)

    if state:
        step = state["step"]
        if step == "phone":
            try:
                await user.connect()
                sent = await user.send_code(text)
                login_state[uid] = {"step": "code", "phone": text, "phone_code_hash": sent.phone_code_hash}
                await message.answer("📩 Telegramdan kod keldi. Yuboring:")
            except Exception as e:
                await user.disconnect()
                del login_state[uid]
                await message.answer(f"❌ {e}")
            return
        if step == "code":
            try:
                await user.sign_in(state["phone"], state["phone_code_hash"], text.replace(" ", ""))
                del login_state[uid]
                me = await user.get_me()
                await message.answer(f"✅ Ulandi! Salom, {me.first_name}!")
            except SessionPasswordNeeded:
                login_state[uid]["step"] = "password"
                await message.answer("🔐 2FA parolingiz:")
            except (PhoneCodeInvalid, PhoneCodeExpired):
                del login_state[uid]
                await user.disconnect()
                await message.answer("❌ Kod xato. /login")
            except Exception as e:
                del login_state[uid]
                await user.disconnect()
                await message.answer(f"❌ {e}")
            return
        if step == "password":
            try:
                await user.check_password(text)
                del login_state[uid]
                me = await user.get_me()
                await message.answer(f"✅ Ulandi! {me.first_name}")
            except Exception as e:
                await message.answer(f"❌ {e}")
            return

    chat_id, msg_id = parse_tme_link(text)
    if not chat_id:
        await message.answer("❓ Havola yuboring yoki /topic [havola]")
        return
    if not await user.is_connected():
        await message.answer("❌ /login yozing.")
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

# ── Main ──
async def main():
    if os.path.exists(f"{SESSION_NAME}.session"):
        try:
            await user.start()
            print("✅ User session yuklandi")
        except Exception as e:
            print(f"⚠️ Session xato: {e}")

    print("🤖 Bot ishga tushdi, polling boshlandi...")
    await dp.start_polling(bot)

asyncio.run(main())
