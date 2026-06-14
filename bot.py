import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

# ─── CONFIG ───────────────────────────────────────────────
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
SESSION_NAME = "user_session"

print(f"✅ CONFIG: API_ID={API_ID}, OWNER_ID={OWNER_ID}, BOT_TOKEN={'set' if BOT_TOKEN else 'MISSING'}")

# ─── CLIENTS ──────────────────────────────────────────────
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

login_state = {}
pending_topics = {}  # tasdiqlash kutayotgan topic so'rovlar

def owner_only(func):
    async def wrapper(client, message):
        uid = message.from_user.id
        print(f"📩 Xabar keldi: from_id={uid}, OWNER_ID={OWNER_ID}, match={uid == OWNER_ID}")
        if uid != OWNER_ID:
            await message.reply("❌ Ruxsat yo'q.")
            return
        return await func(client, message)
    wrapper.__name__ = func.__name__
    return wrapper

def parse_tme_link(text):
    """t.me havolasidan chat_id va msg_id oladi"""
    pattern = r"https?://t\.me/(c/(\d+)|([^/]+))/(\d+)"
    match = re.search(pattern, text)
    if not match:
        return None, None
    if match.group(2):
        chat_id = int("-100" + match.group(2))
    else:
        chat_id = match.group(3)
    msg_id = int(match.group(4))
    return chat_id, msg_id

# ─── /start ───────────────────────────────────────────────
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    print(f"📩 /start keldi: {message.from_user.id}")
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Ruxsat yo'q.")
        return
    if await user.is_connected():
        await message.reply(
            "✅ Akkauntga ulangan.\n\n"
            "📌 Buyruqlar:\n"
            "• Havola → bitta xabar mediani olish\n"
            "• /topic [havola] → topic ichidagi barcha medialar\n"
            "• /status → holat\n"
            "• /logout → chiqish"
        )
    else:
        await message.reply("👋 Salom! Boshlash uchun /login yozing.")

# ─── /status ──────────────────────────────────────────────
@bot.on_message(filters.command("status"))
@owner_only
async def status(client, message: Message):
    if await user.is_connected():
        me = await user.get_me()
        await message.reply(f"✅ Ulangan: {me.first_name} ({me.phone_number})")
    else:
        await message.reply("❌ Akkaunt ulanmagan. /login yozing.")

# ─── /login ───────────────────────────────────────────────
@bot.on_message(filters.command("login"))
@owner_only
async def login_start(client, message: Message):
    if await user.is_connected():
        await message.reply("✅ Allaqachon ulangansiz. /logout bilan chiqishingiz mumkin.")
        return
    login_state[message.from_user.id] = {"step": "phone"}
    await message.reply("📱 Telefon raqamingizni yuboring:\nMasalan: `+998901234567`", parse_mode="markdown")

# ─── /logout ──────────────────────────────────────────────
@bot.on_message(filters.command("logout"))
@owner_only
async def logout(client, message: Message):
    if await user.is_connected():
        await user.stop()
        if os.path.exists(f"{SESSION_NAME}.session"):
            os.remove(f"{SESSION_NAME}.session")
        await message.reply("🔓 Akkauntdan chiqdingiz.")
    else:
        await message.reply("Akkaunt ulangan emas.")

# ─── /topic ───────────────────────────────────────────────
@bot.on_message(filters.command("topic"))
@owner_only
async def topic_command(client, message: Message):
    if not await user.is_connected():
        await message.reply("❌ Akkaunt ulanmagan. /login yozing.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❗ Havola yuboring:\n`/topic https://t.me/c/1234567890/456`", parse_mode="markdown")
        return

    chat_id, thread_id = parse_tme_link(args[1])
    if not chat_id:
        await message.reply("❌ Havola noto'g'ri.")
        return

    processing = await message.reply("🔍 Topic tekshirilmoqda...")

    try:
        # Topic ichidagi barcha xabarlarni sanaymiz
        media_msgs = []
        async for msg in user.get_chat_history(chat_id, limit=1000):
            if msg.reply_to_message_id == thread_id or msg.id == thread_id:
                if msg.media:
                    media_msgs.append(msg.id)

        media_msgs.sort()  # tartibda

        if not media_msgs:
            await processing.edit("❌ Bu topicda media topilmadi.")
            return

        count = len(media_msgs)

        if count <= 50:
            # Tasdiqlash so'ramaymiz, to'g'ridan-to'g'ri yuboramiz
            await processing.edit(f"📦 {count} ta media topildi. Yuborilmoqda...")
            await send_topic_media(message, chat_id, media_msgs, processing)
        else:
            # Tasdiqlash so'raymiz
            pending_topics[message.from_user.id] = {
                "chat_id": chat_id,
                "media_msgs": media_msgs,
            }
            await processing.edit(
                f"⚠️ Bu topicda **{count} ta** media bor.\nHammasi yuborilsinmi?",
                parse_mode="markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Ha, yuborish", callback_data="topic_confirm"),
                        InlineKeyboardButton("❌ Bekor", callback_data="topic_cancel"),
                    ]
                ])
            )

    except Exception as e:
        await processing.edit(f"❌ Xato: {e}")

async def send_topic_media(message, chat_id, media_msgs, status_msg):
    """Media larni ketma-ket yuboradi"""
    total = len(media_msgs)
    sent = 0
    failed = 0

    for msg_id in media_msgs:
        try:
            await user.copy_message(
                chat_id=message.chat.id,
                from_chat_id=chat_id,
                message_id=msg_id,
            )
            sent += 1
            await asyncio.sleep(0.5)  # flood limitdan saqlanish
        except Exception:
            failed += 1

    result = f"✅ Yuborildi: {sent}/{total}"
    if failed:
        result += f"\n❌ Xato: {failed} ta"
    await status_msg.edit(result)

# ─── CALLBACK (tasdiqlash) ────────────────────────────────
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("❌ Ruxsat yo'q.")
        return

    data = callback_query.data
    uid = callback_query.from_user.id

    if data == "topic_cancel":
        pending_topics.pop(uid, None)
        await callback_query.message.edit("❌ Bekor qilindi.")

    elif data == "topic_confirm":
        pending = pending_topics.pop(uid, None)
        if not pending:
            await callback_query.message.edit("❌ So'rov topilmadi.")
            return

        total = len(pending["media_msgs"])
        await callback_query.message.edit(f"📦 {total} ta media yuborilmoqda...")
        await send_topic_media(
            callback_query.message,
            pending["chat_id"],
            pending["media_msgs"],
            callback_query.message
        )

    await callback_query.answer()

# ─── MATN XABARLAR (login flow + single link) ─────────────
@bot.on_message(filters.text & ~filters.command(["start","login","logout","status","topic"]))
@owner_only
async def handle_text(client, message: Message):
    uid = message.from_user.id
    text = message.text.strip()

    # ── Login flow ──
    state = login_state.get(uid)
    if state:
        step = state["step"]

        if step == "phone":
            try:
                await user.connect()
                sent = await user.send_code(text)
                login_state[uid] = {"step": "code", "phone": text, "phone_code_hash": sent.phone_code_hash}
                await message.reply("📩 Telegramdan kod keldi. Kodni yuboring:")
            except Exception as e:
                await user.disconnect()
                del login_state[uid]
                await message.reply(f"❌ Xato: {e}")
            return

        if step == "code":
            code = text.replace(" ", "")
            try:
                await user.sign_in(state["phone"], state["phone_code_hash"], code)
                del login_state[uid]
                me = await user.get_me()
                await message.reply(f"✅ Ulandi! Salom, {me.first_name}!\nEndi havola yuboring.")
            except SessionPasswordNeeded:
                login_state[uid]["step"] = "password"
                await message.reply("🔐 2FA parolingizni yuboring:")
            except (PhoneCodeInvalid, PhoneCodeExpired):
                del login_state[uid]
                await user.disconnect()
                await message.reply("❌ Kod noto'g'ri yoki muddati o'tgan. /login dan qayta boshlang.")
            except Exception as e:
                del login_state[uid]
                await user.disconnect()
                await message.reply(f"❌ Xato: {e}")
            return

        if step == "password":
            try:
                await user.check_password(text)
                del login_state[uid]
                me = await user.get_me()
                await message.reply(f"✅ Ulandi! Salom, {me.first_name}!\nEndi havola yuboring.")
            except Exception as e:
                await message.reply(f"❌ Parol xato: {e}")
            return

    # ── Single link ──
    chat_id, msg_id = parse_tme_link(text)
    if not chat_id:
        await message.reply(
            "❓ Telegram xabar havolasini yuboring.\n"
            "Masalan: `https://t.me/c/1234567890/123`\n\n"
            "Topic uchun: `/topic https://t.me/c/1234567890/123`",
            parse_mode="markdown"
        )
        return

    if not await user.is_connected():
        await message.reply("❌ Akkaunt ulanmagan. /login yozing.")
        return

    processing = await message.reply("⏳ Olinmoqda...")
    try:
        msg = await user.get_messages(chat_id, msg_id)
        if msg.empty:
            await processing.edit("❌ Xabar topilmadi.")
            return
        await user.copy_message(
            chat_id=message.chat.id,
            from_chat_id=chat_id,
            message_id=msg_id,
        )
        await processing.delete()
    except Exception as e:
        await processing.edit(f"❌ Xato: {e}")

# ─── MAIN ─────────────────────────────────────────────────
async def main():
    if os.path.exists(f"{SESSION_NAME}.session"):
        try:
            await user.start()
            print("✅ User session yuklandi")
        except Exception as e:
            print(f"⚠️ Session yuklashda xato: {e}")

    await bot.start()
    print("🤖 Bot ishga tushdi")

    await asyncio.Event().wait()

    await bot.stop()
    if await user.is_connected():
        await user.stop()

if __name__ == "__main__":
    asyncio.run(main())
