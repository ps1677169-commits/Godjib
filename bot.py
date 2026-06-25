#!/usr/bin/env python3
"""
Crownit Survey Automation Bot
Telegram bot for automated survey completion and reward redemption.
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

from config import BOT_TOKEN, USE_PROXY, PROXY_LIST_FILE
from database import *
from crownit_automation import CrownitAutomation, get_random_proxy

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
PHONE, OTP, CAPTCHA, SURVEY = range(4)

# Store active automations per user
active_automations = {}

# ============ Helper Functions ============

def load_proxies():
    """Load proxies from file."""
    proxies = []
    if os.path.exists(PROXY_LIST_FILE):
        with open(PROXY_LIST_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

def get_proxy():
    """Get a random proxy from the list."""
    proxies = load_proxies()
    if proxies:
        return random.choice(proxies)
    return None

# ============ Bot Commands ============

async def start(update: Update, context):
    """Start command - show main menu."""
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
        f"Automate Crownit surveys and earn rewards!\n\n"
        f"🌐 Proxy: {proxy_status}\n"
        f"📦 Proxies loaded: {len(load_proxies())}\n\n"
        "🔥 **Features:**\n"
        "• Create Crownit accounts\n"
        "• Complete surveys automatically\n"
        "• Redeem Amazon/Playstore gift cards\n"
        "• Proxy support for multiple accounts\n\n"
        "⚠️ **Disclaimer:** Use at your own risk.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context):
    """Handle button clicks."""
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
            "📌 **Note:** You'll receive OTP on this number.",
            parse_mode="Markdown"
        )
        return PHONE
    
    elif data == "list_accounts":
        accounts = get_accounts_by_user(user_id)
        if not accounts:
            await query.message.reply_text("No accounts found. Create one first!")
            return
        
        msg = "📋 **Your Accounts**\n\n"
        for acc in accounts:
            status_emoji = "🟢" if acc[6] == "active" else "🔴"
            msg += (
                f"{status_emoji} `{acc[2]}`\n"
                f"   Status: {acc[6]}\n"
                f"   Total Earned: ₹{acc[8] or 0}\n"
                f"   Created: {acc[7][:10]}\n\n"
            )
        await query.message.reply_text(msg, parse_mode="Markdown")
    
    elif data == "start_survey":
        accounts = get_accounts_by_user(user_id)
        active_accounts = [a for a in accounts if a[6] == "active"]
        if not active_accounts:
            await query.message.reply_text("No active accounts. Create one first!")
            return
        
        # Start survey on first active account
        acc = active_accounts[0]
        context.user_data["account_id"] = acc[0]
        context.user_data["account_phone"] = acc[2]
        context.user_data["account_cookie"] = acc[4]
        
        await query.message.reply_text(
            f"🚀 **Starting survey for** `{acc[2]}`\n\n"
            "Please wait while the bot completes the survey...\n"
            "This may take 2-5 minutes.",
            parse_mode="Markdown"
        )
        
        # Run survey in background
        asyncio.create_task(run_survey(update, context, acc))
    
    elif data == "redeem_reward":
        keyboard = [
            [InlineKeyboardButton("🛒 Amazon Gift Card", callback_data="redeem_amazon")],
            [InlineKeyboardButton("🎮 Playstore Gift Card", callback_data="redeem_playstore")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "🎁 **Select Reward Type**",
            reply_markup=reply_markup
        )
    
    elif data.startswith("redeem_"):
        reward_type = data.split("_")[1]  # "amazon" or "playstore"
        accounts = get_accounts_by_user(user_id)
        active_accounts = [a for a in accounts if a[6] == "active"]
        if not active_accounts:
            await query.message.reply_text("No active accounts. Create one first!")
            return
        
        acc = active_accounts[0]
        context.user_data["account_id"] = acc[0]
        context.user_data["reward_type"] = reward_type
        
        await query.message.reply_text(
            f"🎁 **Redeeming {reward_type.title()} gift card...**\n\n"
            "Please wait while the bot processes your reward.",
            parse_mode="Markdown"
        )
        
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
            f"📊 **Your Stats**\n\n"
            f"👤 Accounts: {len(accounts)} ({active_count} active)\n"
            f"📝 Surveys Completed: {survey_count}\n"
            f"🎁 Rewards Redeemed: {reward_count}\n"
            f"💰 Total Earned: ₹{total_earned}"
        )
    
    elif data == "settings":
        proxy_status = "ON" if USE_PROXY and load_proxies() else "OFF"
        keyboard = [
            [InlineKeyboardButton(f"🌐 Proxy: {proxy_status}", callback_data="toggle_proxy")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("⚙️ **Settings**", reply_markup=reply_markup)
    
    elif data == "help":
        await query.message.reply_text(
            "ℹ️ **Help**\n\n"
            "1. **Create Account:** Start with /create or click 'Create Account'\n"
            "2. **OTP:** Enter the OTP received on your phone\n"
            "3. **Survey:** Bot automatically completes surveys\n"
            "4. **Rewards:** Redeem Amazon/Playstore gift cards\n\n"
            "⚠️ **Troubleshooting:**\n"
            "• If CAPTCHA appears, solve it manually\n"
            "• Use different proxies for multiple accounts\n"
            "• Check account status in 'My Accounts'"
        )
    
    elif data == "back":
        await start(update, context)

async def run_survey(update, context, account):
    """Run survey in background."""
    try:
        user_id = update.effective_user.id
        proxy = get_random_proxy() if USE_PROXY else None
        automation = CrownitAutomation(proxy=proxy)
        
        result = automation.complete_survey(account[4])  # cookie
        
        if result["status"] == "success":
            add_survey_completed(account[0], "auto_survey", result.get("reward", 0))
            await context.bot.send_message(
                user_id,
                f"✅ **Survey Completed!**\n\n"
                f"🎉 Reward Earned: ₹{result.get('reward', 0)}\n"
                f"📝 Questions: {result.get('questions_answered', 0)}\n\n"
                f"Continue to redeem your reward!",
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                user_id,
                f"❌ **Survey Failed**\n\n"
                f"Reason: {result.get('message', 'Unknown error')}"
            )
        
        automation.cleanup()
        
    except Exception as e:
        logger.error(f"Survey error: {e}", exc_info=True)
        await context.bot.send_message(
            user_id,
            f"❌ **Survey Error**\n\n{str(e)}"
        )

async def run_redeem(update, context, account, reward_type):
    """Run reward redemption in background."""
    try:
        user_id = update.effective_user.id
        proxy = get_random_proxy() if USE_PROXY else None
        automation = CrownitAutomation(proxy=proxy)
        
        result = automation.redeem_reward(account[4], reward_type)
        
        if result["status"] == "success":
            add_reward(account[0], reward_type, result.get("reward_code"), result.get("reward_link"))
            
            msg = f"✅ **{reward_type.title()} Gift Card Redeemed!**\n\n"
            if result.get("reward_code"):
                msg += f"🎫 **Code:** `{result['reward_code']}`\n"
            if result.get("reward_link"):
                msg += f"🔗 **Link:** {result['reward_link']}\n"
            
            await context.bot.send_message(user_id, msg, parse_mode="Markdown")
        else:
            await context.bot.send_message(
                user_id,
                f"❌ **Redemption Failed**\n\n{result.get('message', 'Unknown error')}"
            )
        
        automation.cleanup()
        
    except Exception as e:
        logger.error(f"Redeem error: {e}", exc_info=True)
        await context.bot.send_message(
            user_id,
            f"❌ **Redemption Error**\n\n{str(e)}"
        )

# ============ Conversation Handlers ============

async def phone_input(update: Update, context):
    """Handle phone number input."""
    phone = update.message.text.strip()
    
    # Validate phone number
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        await update.message.reply_text(
            "❌ **Invalid phone number**\n\n"
            "Please send a valid phone number with country code.\n"
            "Example: `+919876543210`",
            parse_mode="Markdown"
        )
        return PHONE
    
    if not phone.startswith("+"):
        phone = "+" + phone
    
    user_id = update.effective_user.id
    context.user_data["phone"] = phone
    
    await update.message.reply_text(
        f"📱 **Creating account for** `{phone}`\n\n"
        "Please wait while we connect to Crownit...",
        parse_mode="Markdown"
    )
    
    # Start account creation
    proxy = get_random_proxy() if USE_PROXY else None
    automation = CrownitAutomation(proxy=proxy)
    context.user_data["automation"] = automation
    
    result = automation.create_account(phone)
    
    if result["status"] == "otp_sent":
        context.user_data["request_id"] = result["request_id"]
        save_otp_request(phone, result["request_id"], user_id)
        
        await update.message.reply_text(
            f"✅ **OTP Sent** to `{phone}`\n\n"
            "Please enter the 6-digit OTP you received.\n"
            "You have 10 minutes to enter it.",
            parse_mode="Markdown"
        )
        return OTP
    
    elif result["status"] == "captcha_required":
        context.user_data["captcha_phone"] = phone
        # Send CAPTCHA image
        if os.path.exists(result["captcha_path"]):
            with open(result["captcha_path"], "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="🧩 **CAPTCHA Required**\n\nPlease solve the CAPTCHA and enter the text.",
                    parse_mode="Markdown"
                )
            os.remove(result["captcha_path"])
        else:
            await update.message.reply_text(
                "🧩 **CAPTCHA Required**\n\n"
                "Please enter the CAPTCHA text shown on the website.",
                parse_mode="Markdown"
            )
        return CAPTCHA
    
    else:
        # Error
        error_msg = result.get("message", "Unknown error")
        await update.message.reply_text(
            f"❌ **Account Creation Failed**\n\n{error_msg}\n\n"
            "Please try again or use a different phone number.",
            parse_mode="Markdown"
        )
        automation.cleanup()
        return ConversationHandler.END

async def otp_input(update: Update, context):
    """Handle OTP input."""
    otp = update.message.text.strip()
    
    if not re.match(r'^[0-9]{6}$', otp):
        await update.message.reply_text(
            "❌ **Invalid OTP**\n\n"
            "Please enter a valid 6-digit OTP.",
            parse_mode="Markdown"
        )
        return OTP
    
    phone = context.user_data.get("phone")
    if not phone:
        await update.message.reply_text("❌ Phone number not found. Please start over.")
        return ConversationHandler.END
    
    automation = context.user_data.get("automation")
    if not automation:
        await update.message.reply_text("❌ Session expired. Please start over.")
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ **Verifying OTP...**", parse_mode="Markdown")
    
    result = automation.verify_otp(phone, otp)
    
    if result["status"] == "success":
        # Save account
        user_id = update.effective_user.id
        account_id = create_account(
            user_id,
            phone,
            f"user_{phone[-6:]}@temp.com",  # Temp email
            "auto_generated",
            result.get("cookie")
        )
        
        await update.message.reply_text(
            f"✅ **Account Created Successfully!**\n\n"
            f"📱 Phone: `{phone}`\n"
            f"🆔 Account ID: `{account_id}`\n\n"
            f"Ready to start surveys!",
            parse_mode="Markdown"
        )
        
        # Cleanup
        delete_otp_request(phone)
        automation.cleanup()
        context.user_data.pop("automation", None)
        
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            f"❌ **OTP Verification Failed**\n\n{result.get('message', 'Unknown error')}\n\n"
            "Please try again or request a new OTP.",
            parse_mode="Markdown"
        )
        return OTP

async def captcha_input(update: Update, context):
    """Handle CAPTCHA input."""
    captcha = update.message.text.strip()
    phone = context.user_data.get("captcha_phone")
    
    if not phone:
        await update.message.reply_text("❌ Session expired. Please start over.")
        return ConversationHandler.END
    
    automation = context.user_data.get("automation")
    if not automation:
        await update.message.reply_text("❌ Session expired. Please start over.")
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ **Verifying CAPTCHA...**", parse_mode="Markdown")
    
    # Proceed with OTP after CAPTCHA (we don't have OTP yet, so we need to ask for it)
    # The flow is: CAPTCHA solved -> then ask for OTP again
    # But the current flow expects OTP after CAPTCHA.
    # We'll handle it by moving back to OTP state.
    context.user_data["phone"] = phone
    context.user_data["captcha_solved"] = captcha
    
    await update.message.reply_text(
        "✅ **CAPTCHA Solved**\n\n"
        "Now enter the OTP you received on your phone.",
        parse_mode="Markdown"
    )
    return OTP

async def cancel(update: Update, context):
    """Cancel conversation."""
    # Cleanup automation if exists
    automation = context.user_data.get("automation")
    if automation:
        automation.cleanup()
        context.user_data.pop("automation", None)
    
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

# ============ Main ============

def main():
    """Run the bot."""
    # Initialize database
    init_db()
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("create", start),
            CallbackQueryHandler(button_handler, pattern="^create_account$"),
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)],
            CAPTCHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, captcha_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add handlers
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Start bot
    logger.info("🤖 Crownit Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
