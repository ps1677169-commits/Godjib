#!/usr/bin/env python3
"""
Crownit Survey Automation Bot – Final
Supports registration via onboarding, OTP, survey with user callback.
"""
import os
import re
import json
import logging
import asyncio
import random
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from dotenv import load_dotenv

from config import BOT_TOKEN, USE_PROXY
from database import *
from crownit_automation import CrownitAutomation, get_random_proxy

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
PHONE, OTP, CAPTCHA, AWAITING_SURVEY_ANSWER = range(4)

# ============ Helper Functions ============

def load_proxies():
    proxies = []
    if os.path.exists(PROXY_LIST_FILE):
        with open(PROXY_LIST_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

def get_proxy():
    proxies = load_proxies()
    if proxies:
        return random.choice(proxies)
    return None

# ============ Bot Commands ============

async def start(update: Update, context):
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("📱 Create Account", callback_data="create_account")],
        [InlineKeyboardButton("📋 My Accounts", callback_data="list_accounts")],
        [InlineKeyboardButton("🚀 Start Survey", callback_data="start_survey")],
        [InlineKeyboardButton("🎁 Redeem Reward", callback_data="redeem_reward")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    proxy_status = "✅ Enabled" if USE_PROXY and load_proxies() else "❌ Disabled"
    
    await update.message.reply_text(
        f"🎯 **Crownit Survey Bot**\n\n"
        f"Automate Crownit registration, surveys and rewards!\n\n"
        f"🌐 Proxy: {proxy_status}\n"
        f"📦 Proxies loaded: {len(load_proxies())}\n\n"
        "🔥 **Features:**\n"
        "• Create Crownit accounts with random details\n"
        "• Complete surveys automatically\n"
        "• Redeem Amazon/Playstore gift cards\n"
        "• Unknown questions sent to you for input\n\n"
        "⚠️ Use at your own risk.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "create_account":
        context.user_data["action"] = "create_account"
        await query.message.reply_text(
            "📱 **Create Crownit Account**\n\n"
            "Send your phone number with country code:\n"
            "Example: `+919876543210`\n\n"
            "📌 You'll receive OTP on this number.",
            parse_mode="Markdown"
        )
        return PHONE

    elif data == "list_accounts":
        accounts = get_accounts_by_user(user_id)
        if not accounts:
            await query.message.reply_text("No accounts found.")
            return
        msg = "📋 **Your Accounts**\n\n"
        for acc in accounts:
            status_emoji = "🟢" if acc[6] == "active" else "🔴"
            msg += f"{status_emoji} `{acc[2]}`\n   Status: {acc[6]}\n   Earned: ₹{acc[8] or 0}\n\n"
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "start_survey":
        accounts = get_accounts_by_user(user_id)
        active = [a for a in accounts if a[6] == "active"]
        if not active:
            await query.message.reply_text("No active accounts. Create one first!")
            return
        acc = active[0]
        context.user_data["account_id"] = acc[0]
        context.user_data["account_phone"] = acc[2]
        context.user_data["account_cookie"] = acc[4]
        await query.message.reply_text(f"🚀 **Starting survey for** `{acc[2]}`...")
        asyncio.create_task(run_survey(update, context, acc))

    elif data == "redeem_reward":
        keyboard = [
            [InlineKeyboardButton("🛒 Amazon Gift Card", callback_data="redeem_amazon")],
            [InlineKeyboardButton("🎮 Playstore Gift Card", callback_data="redeem_playstore")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        await query.message.reply_text("🎁 **Select Reward Type**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("redeem_"):
        reward_type = data.split("_")[1]
        accounts = get_accounts_by_user(user_id)
        active = [a for a in accounts if a[6] == "active"]
        if not active:
            await query.message.reply_text("No active accounts.")
            return
        acc = active[0]
        context.user_data["account_id"] = acc[0]
        context.user_data["reward_type"] = reward_type
        await query.message.reply_text(f"🎁 Redeeming {reward_type.title()} gift card...")
        asyncio.create_task(run_redeem(update, context, acc, reward_type))

    elif data == "stats":
        accounts = get_accounts_by_user(user_id)
        total_earned = sum(a[8] or 0 for a in accounts)
        active_count = len([a for a in accounts if a[6] == "active"])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM surveys WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (user_id,))
        survey_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM rewards WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (user_id,))
        reward_count = c.fetchone()[0]
        conn.close()
        await query.message.reply_text(
            f"📊 **Stats**\n\n"
            f"👤 Accounts: {len(accounts)} ({active_count} active)\n"
            f"📝 Surveys: {survey_count}\n"
            f"🎁 Rewards: {reward_count}\n"
            f"💰 Total Earned: ₹{total_earned}"
        )

    elif data == "settings":
        proxy_status = "ON" if USE_PROXY and load_proxies() else "OFF"
        keyboard = [
            [InlineKeyboardButton(f"🌐 Proxy: {proxy_status}", callback_data="toggle_proxy")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        await query.message.reply_text("⚙️ **Settings**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help":
        await query.message.reply_text(
            "ℹ️ **Help**\n\n"
            "1. Create Account → enter phone\n"
            "2. Enter OTP received\n"
            "3. Bot registers and completes surveys automatically\n"
            "4. If survey question is unknown, bot asks you for input\n"
            "5. Redeem rewards"
        )

    elif data == "back":
        await start(update, context)

# ============ Background Tasks ============

async def run_survey(update, context, account):
    """Run survey with user callback."""
    try:
        user_id = update.effective_user.id
        proxy = get_random_proxy() if USE_PROXY else None
        
        # Create automation with user callback
        automation = CrownitAutomation(
            proxy=proxy,
            user_callback=context.bot.send_message
        )
        automation.cookie = account[4]  # Store for continuation
        
        result = automation.complete_survey(account[4], user_id=user_id)
        
        if result["status"] == "pending_user_input":
            # Save context for user reply
            context.user_data["pending_automation"] = automation
            context.user_data["pending_question"] = result["question"]
            context.user_data["pending_question_count"] = result["question_count"]
            context.user_data["pending_account_id"] = account[0]
            # State is handled by the conversation handler
            return
        
        if result["status"] == "success":
            add_survey_completed(account[0], "auto_survey", result.get("reward", 0))
            await context.bot.send_message(
                user_id,
                f"✅ **Survey Done!**\n🎉 Reward: ₹{result.get('reward', 0)}\n📝 Q: {result.get('questions_answered', 0)}"
            )
        else:
            await context.bot.send_message(user_id, f"❌ Survey failed: {result.get('message')}")
        
        automation.cleanup()
        
    except Exception as e:
        logger.error(f"Survey error: {e}", exc_info=True)
        await context.bot.send_message(user_id, f"❌ Error: {str(e)}")

async def run_redeem(update, context, account, reward_type):
    try:
        user_id = update.effective_user.id
        proxy = get_random_proxy() if USE_PROXY else None
        automation = CrownitAutomation(proxy=proxy)
        result = automation.redeem_reward(account[4], reward_type)
        if result["status"] == "success":
            add_reward(account[0], reward_type, result.get("reward_code"), result.get("reward_link"))
            msg = f"✅ {reward_type.title()} Gift Card!\n"
            if result.get("reward_code"):
                msg += f"🎫 Code: `{result['reward_code']}`\n"
            if result.get("reward_link"):
                msg += f"🔗 Link: {result['reward_link']}\n"
            await context.bot.send_message(user_id, msg, parse_mode="Markdown")
        else:
            await context.bot.send_message(user_id, f"❌ Redemption failed: {result.get('message')}")
        automation.cleanup()
    except Exception as e:
        logger.error(f"Redeem error: {e}", exc_info=True)
        await context.bot.send_message(user_id, f"❌ Error: {str(e)}")

# ============ Conversation Handlers ============

async def phone_input(update: Update, context):
    phone = update.message.text.strip()
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        await update.message.reply_text("❌ Invalid phone. Use `+919876543210`", parse_mode="Markdown")
        return PHONE
    if not phone.startswith("+"):
        phone = "+" + phone
    context.user_data["phone"] = phone
    await update.message.reply_text(f"📱 Creating account for `{phone}`...", parse_mode="Markdown")

    proxy = get_random_proxy() if USE_PROXY else None
    automation = CrownitAutomation(proxy=proxy)
    context.user_data["automation"] = automation
    
    result = automation.register_and_verify(phone)

    if result["status"] == "otp_sent":
        context.user_data["request_id"] = result["request_id"]
        save_otp_request(phone, result["request_id"], update.effective_user.id)
        await update.message.reply_text(
            f"✅ OTP sent to `{phone}`\nEnter the 6-digit OTP.",
            parse_mode="Markdown"
        )
        return OTP

    elif result["status"] == "captcha_required":
        context.user_data["captcha_phone"] = phone
        if os.path.exists(result["captcha_path"]):
            with open(result["captcha_path"], "rb") as f:
                await update.message.reply_photo(f, caption="🧩 CAPTCHA required. Enter the text.")
            os.remove(result["captcha_path"])
        else:
            await update.message.reply_text("🧩 CAPTCHA required. Enter the text.")
        return CAPTCHA

    elif result["status"] == "success":
        # Already logged in (unlikely during registration)
        user_id = update.effective_user.id
        account_id = create_account(
            user_id,
            phone,
            f"user_{phone[-6:]}@temp.com",
            "auto_generated",
            result.get("cookie")
        )
        await update.message.reply_text(
            f"✅ Account already exists! Logged in.\n📱 `{phone}`\n🆔 ID: `{account_id}`",
            parse_mode="Markdown"
        )
        automation.cleanup()
        return ConversationHandler.END

    else:
        error_msg = result.get("message", "Unknown error")
        logger.error(f"Registration error: {error_msg}")
        await update.message.reply_text(f"❌ Registration Failed\n\n{error_msg}\n\nPlease try again.")
        automation.cleanup()
        return ConversationHandler.END

async def otp_input(update: Update, context):
    otp = update.message.text.strip()
    if not re.match(r'^[0-9]{6}$', otp):
        await update.message.reply_text("❌ Invalid OTP. Enter 6 digits.")
        return OTP
    
    phone = context.user_data.get("phone")
    if not phone:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END
    
    automation = context.user_data.get("automation")
    if not automation:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END

    await update.message.reply_text("⏳ Verifying OTP...")
    result = automation.verify_otp(phone, otp)
    
    if result["status"] == "success":
        user_id = update.effective_user.id
        account_id = create_account(
            user_id,
            phone,
            f"user_{phone[-6:]}@temp.com",
            "auto_generated",
            result.get("cookie")
        )
        await update.message.reply_text(
            f"✅ Account Created!\n📱 `{phone}`\n🆔 ID: `{account_id}`\n\nNow you can start surveys.",
            parse_mode="Markdown"
        )
        delete_otp_request(phone)
        automation.cleanup()
        context.user_data.pop("automation", None)
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"❌ OTP Failed: {result.get('message', 'Unknown error')}")
        return OTP

async def captcha_input(update: Update, context):
    captcha = update.message.text.strip()
    phone = context.user_data.get("captcha_phone")
    if not phone:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END
    automation = context.user_data.get("automation")
    if not automation:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END

    context.user_data["phone"] = phone
    context.user_data["captcha_solved"] = captcha
    await update.message.reply_text("✅ CAPTCHA solved. Now enter the OTP.")
    return OTP

async def survey_answer_input(update: Update, context):
    """Handle user's reply to a survey question."""
    user_id = update.effective_user.id
    answer = update.message.text.strip()
    
    if not answer:
        await update.message.reply_text("❌ Please provide a valid answer.")
        return AWAITING_SURVEY_ANSWER
    
    automation = context.user_data.get("pending_automation")
    if not automation:
        await update.message.reply_text("❌ Session expired. Please start a new survey.")
        return ConversationHandler.END
    
    # Resume survey with the answer
    result = automation.continue_survey_with_answer(user_id, answer)
    
    if result["status"] == "success":
        add_survey_completed(
            context.user_data.get("pending_account_id"),
            "auto_survey",
            result.get("reward", 0)
        )
        await update.message.reply_text(
            f"✅ **Survey Completed!**\n🎉 Reward: ₹{result.get('reward', 0)}\n📝 Q: {result.get('questions_answered', 0)}"
        )
        automation.cleanup()
        context.user_data.pop("pending_automation", None)
        context.user_data.pop("pending_question", None)
        return ConversationHandler.END
    elif result["status"] == "pending_user_input":
        # Another question needs input
        await update.message.reply_text(
            f"❓ **Another question needs your input**\n\n"
            f"📝 **Question:** {result.get('question', 'Unknown')}\n\n"
            f"Please reply with your answer."
        )
        context.user_data["pending_question"] = result["question"]
        return AWAITING_SURVEY_ANSWER
    else:
        await update.message.reply_text(f"❌ Survey error: {result.get('message', 'Unknown error')}")
        automation.cleanup()
        context.user_data.pop("pending_automation", None)
        return ConversationHandler.END

async def cancel(update: Update, context):
    automation = context.user_data.get("automation")
    if automation:
        automation.cleanup()
        context.user_data.pop("automation", None)
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ============ Main ============

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler – updated with survey answer state
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("create", start),
            CallbackQueryHandler(button_handler, pattern="^create_account$"),
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)],
            CAPTCHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, captcha_input)],
            AWAITING_SURVEY_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_answer_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Crownit Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
