import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
SESSION_NAME = "user_session"

print(f"✅ CONFIG: API_ID={API_ID}, OWNER_ID={OWNER_ID}")

app = Client("mybot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
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

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    print(f"📩 /start: {message.from_user.id}")
    if message.from_user.id != OWNER_ID:
        return
    if await user.is_connected():
        await message.reply("✅ Ulangan.\n\n• Havola → bitta media\n• /topic [havola] → topic\n• /status\n• /logout")
    else:
        await message.reply("👋 /login yozing.")

@app.on_message(filters.command("status"))
async def status(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if await user.is_connected():
        me = await user.get_me()
        await message.reply(f"✅ {me.first_name} ({me.phone_number})")
    else:
        await message.reply("❌ Ulanmagan. /login")

@app.on_message(filters.command("login"))
async def login_start(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if await user.is_connected():
        await message.reply("✅ Allaqachon ulangansiz.")
        return
    login_state[message.from_user.id] = {"step": "phone"}
    await message.reply("📱 Telefon raqam:")

@app.on_message(filters.command("logout"))
async def logout(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if await user.is_connected():
        await user.stop()
        if os.path.exists(f"{SESSION_NAME}.session"):
            os.remove(f"{SESSION_NAME}.session")
        await message.reply("🔓 Chiqdingiz.")
    else:
        await message.reply("Ulanmagan.")

@app.on_message(filters.command("topic"))
async def topic_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if not await user.is_connected():
        await message.reply("❌ /login")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❗ /topic [havola]")
        return
    chat_id, thread_id = parse_tme_link(args[1])
    if not chat_id:
        await message.reply("❌ Havola xato.")
        return
    proc = await message.reply("🔍 Tekshirilmoqda...")
    try:
        media_msgs = []
        async for msg in user.get_chat_history(chat_id, limit=1000):
            if (msg.reply_to_message_id == thread_id or msg.id == thread_id) and msg.media:
                media_msgs.append(msg.id)
        media_msgs.sort()
        if not media_msgs:
            await proc.edit("❌ Media topilmadi.")
            return
        count = len(media_msgs)
        if count <= 50:
            await proc.edit(f"📦 {count} ta yuborilmoqda...")
            await send_media(message, chat_id, media_msgs, proc)
        else:
            pending_topics[message.from_user.id] = {"chat_id": chat_id, "media_msgs": media_msgs}
            await proc.edit(
                f"⚠️ **{count} ta** media. Yuborilsinmi?",
                parse_mode="markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Ha", callback_data="topic_yes"),
                    InlineKeyboardButton("❌ Yo'q", callback_data="topic_no"),
                ]])
            )
    except Exception as e:
        await proc.edit(f"❌ {e}")

async def send_media(message, chat_id, media_msgs, status_msg):
    sent = 0
    for msg_id in media_msgs:
        try:
            await user.copy_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=msg_id)
            sent += 1
            await asyncio.sleep(0.5)
        except:
            pass
    await status_msg.edit(f"✅ {sent}/{len(media_msgs)} yuborildi.")

@app.on_callback_query()
async def cb(client, cq):
    if cq.from_user.id != OWNER_ID:
        return
    if cq.data == "topic_no":
        pending_topics.pop(cq.from_user.id, None)
        await cq.message.edit("❌ Bekor.")
    elif cq.data == "topic_yes":
        p = pending_topics.pop(cq.from_user.id, None)
        if not p:
            await cq.message.edit("❌ Topilmadi.")
            return
        await cq.message.edit(f"📦 Yuborilmoqda...")
        await send_media(cq.message, p["chat_id"], p["media_msgs"], cq.message)
    await cq.answer()

@app.on_message(filters.text & ~filters.command(["start","login","logout","status","topic"]))
async def handle_text(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
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
                await message.reply("📩 Kod:")
            except Exception as e:
                await user.disconnect()
                del login_state[uid]
                await message.reply(f"❌ {e}")
            return
        if step == "code":
            try:
                await user.sign_in(state["phone"], state["phone_code_hash"], text.replace(" ", ""))
                del login_state[uid]
                me = await user.get_me()
                await message.reply(f"✅ Ulandi! {me.first_name}")
            except SessionPasswordNeeded:
                login_state[uid]["step"] = "password"
                await message.reply("🔐 2FA parol:")
            except (PhoneCodeInvalid, PhoneCodeExpired):
                del login_state[uid]
                await user.disconnect()
                await message.reply("❌ Kod xato. /login")
            except Exception as e:
                del login_state[uid]
                await user.disconnect()
                await message.reply(f"❌ {e}")
            return
        if step == "password":
            try:
                await user.check_password(text)
                del login_state[uid]
                me = await user.get_me()
                await message.reply(f"✅ Ulandi! {me.first_name}")
            except Exception as e:
                await message.reply(f"❌ {e}")
            return

    chat_id, msg_id = parse_tme_link(text)
    if not chat_id:
        await message.reply("❓ Havola yuboring yoki /topic [havola]")
        return
    if not await user.is_connected():
        await message.reply("❌ /login")
        return
    proc = await message.reply("⏳ Olinmoqda...")
    try:
        msg = await user.get_messages(chat_id, msg_id)
        if msg.empty:
            await proc.edit("❌ Topilmadi.")
            return
        await user.copy_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=msg_id)
        await proc.delete()
    except Exception as e:
        await proc.edit(f"❌ {e}")

async def on_startup():
    if os.path.exists(f"{SESSION_NAME}.session"):
        try:
            await user.start()
            print("✅ User session yuklandi")
        except Exception as e:
            print(f"⚠️ {e}")
    print("🤖 Bot tayyor")

print("▶️ Ishga tushmoqda...")
app.run(on_startup())
