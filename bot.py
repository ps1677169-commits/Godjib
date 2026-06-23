#!/usr/bin/env python3
"""
Telegram Mass Reporter Bot – Full Configurable
Commands:
  /start            – Show help
  /addaccount       – Add a Telegram account (phone, api_id, api_hash, optional proxy)
  /removeaccount    – Remove an account by phone
  /listaccounts     – List all saved accounts
  /addproxy <proxy> – Add a single proxy to the pool
  /proxytxt         – Reply with a .txt file containing proxies
  /listproxies      – Show all proxies
  /clearproxies     – Remove all proxies
  /setcycles <num>  – Set fixed number of report cycles (0 = random 1-5)
  /setrandomcycles  – Toggle random cycles (1-5) – default ON
  /setconcurrency <num> – Set concurrent reports per batch (default 10)
  /settings         – Show current settings
  /startreport <target> <reason> [msg_ids] – Start mass report
  /stopreport       – Stop current report
  /status           – Show report progress
"""

import os
import sys
import json
import asyncio
import logging
import random
from urllib.parse import urlparse
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonOther,
)
from aiohttp_socks import ProxyConnector, ProxyType
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import aiohttp

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "sessions")
ACCOUNTS_JSON = os.getenv("ACCOUNTS_JSON", "accounts_config.json")
PROXY_FILE = os.getenv("PROXY_FILE", "proxies.txt")
SETTINGS_FILE = os.getenv("SETTINGS_FILE", "settings.json")

REPORT_REASONS = {
    1: InputReportReasonSpam(),
    2: InputReportReasonViolence(),
    3: InputReportReasonPornography(),
    4: InputReportReasonChildAbuse(),
    5: InputReportReasonCopyright(),
    6: InputReportReasonOther(),
}
REASON_NAMES = {1: "Spam", 2: "Violence", 3: "Pornography", 4: "Child Abuse", 5: "Copyright", 6: "Other"}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- SETTINGS MANAGER ----------
class SettingsManager:
    def __init__(self, settings_file=SETTINGS_FILE):
        self.settings_file = settings_file
        self.defaults = {
            "random_cycles": True,
            "fixed_cycles": 3,
            "concurrency": 10,
        }
        self.settings = self.load()

    def load(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
                for k, v in self.defaults.items():
                    if k not in data:
                        data[k] = v
                return data
        return self.defaults.copy()

    def save(self):
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def set_fixed_cycles(self, num):
        if num < 0:
            num = 0
        self.settings['fixed_cycles'] = num
        self.settings['random_cycles'] = (num == 0)
        self.save()

    def set_random_cycles(self, enabled):
        self.settings['random_cycles'] = enabled
        if not enabled and self.settings['fixed_cycles'] == 0:
            self.settings['fixed_cycles'] = 3
        self.save()

    def set_concurrency(self, num):
        if num < 1:
            num = 1
        self.settings['concurrency'] = num
        self.save()

    def get_cycles(self):
        if self.settings['random_cycles']:
            return random.randint(1, 5)
        else:
            return max(1, self.settings['fixed_cycles'])

    def get_concurrency(self):
        return self.settings['concurrency']

# ---------- UTILITY FUNCTIONS ----------
def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    parsed = urlparse(proxy_str)
    scheme = parsed.scheme.lower()
    if scheme in ('socks5', 'socks4'):
        return {
            'type': 'socks',
            'proxy_type': ProxyType.SOCKS5 if scheme == 'socks5' else ProxyType.SOCKS4,
            'host': parsed.hostname,
            'port': parsed.port,
            'username': parsed.username,
            'password': parsed.password
        }
    elif scheme in ('http', 'https'):
        return {
            'type': 'http',
            'host': parsed.hostname,
            'port': parsed.port,
            'username': parsed.username,
            'password': parsed.password
        }
    return None

def load_proxies(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_proxies(file_path, proxies):
    with open(file_path, 'w') as f:
        f.write('\n'.join(proxies))

def load_config(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {}

def save_config(file_path, data):
    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

# ---------- ACCOUNT MANAGER ----------
class AccountManager:
    def __init__(self):
        self.sessions_dir = SESSIONS_DIR
        self.accounts_json = ACCOUNTS_JSON
        self.config = load_config(self.accounts_json)
        self.proxies = load_proxies(PROXY_FILE)
        self.proxy_index = 0

    def get_next_proxy(self):
        if not self.proxies:
            return None
        p = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return p

    def add_proxy(self, proxy_str):
        if proxy_str not in self.proxies:
            self.proxies.append(proxy_str)
            save_proxies(PROXY_FILE, self.proxies)
            return True
        return False

    def add_proxies_from_list(self, proxy_list):
        added = 0
        for p in proxy_list:
            if p and p not in self.proxies:
                self.proxies.append(p)
                added += 1
        if added:
            save_proxies(PROXY_FILE, self.proxies)
        return added

    def clear_proxies(self):
        self.proxies = []
        save_proxies(PROXY_FILE, [])

    def get_proxies(self):
        return self.proxies[:]

    def _create_client(self, phone, proxy_str=None):
        creds = self.config.get(phone)
        if not creds:
            raise ValueError(f"No credentials for {phone}")
        api_id = creds['api_id']
        api_hash = creds['api_hash']
        if proxy_str is None:
            proxy_str = creds.get('proxy')
        proxy = None
        connector = None
        if proxy_str:
            parsed = parse_proxy(proxy_str)
            if parsed:
                if parsed['type'] == 'socks':
                    connector = ProxyConnector(
                        proxy_type=parsed['proxy_type'],
                        host=parsed['host'],
                        port=parsed['port'],
                        username=parsed.get('username'),
                        password=parsed.get('password'),
                        rdns=True
                    )
                    proxy = connector
                elif parsed['type'] == 'http':
                    proxy = {
                        'proxy_type': 'http',
                        'addr': parsed['host'],
                        'port': parsed['port'],
                        'username': parsed.get('username'),
                        'password': parsed.get('password')
                    }
        session_file = os.path.join(self.sessions_dir, phone)
        return TelegramClient(session_file, api_id, api_hash, proxy=proxy, connector=connector)

    async def get_all_clients(self, retry_with_new_proxy=True):
        clients = []
        for phone in self.config:
            proxy = self.config[phone].get('proxy')
            if not proxy and self.proxies:
                proxy = self.get_next_proxy()
            try:
                client = self._create_client(phone, proxy)
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(f"{phone} not authorized. Skipping.")
                    continue
                clients.append((phone, client))
            except Exception as e:
                logger.error(f"Error connecting {phone}: {e}")
                if retry_with_new_proxy and self.proxies:
                    new_proxy = self.get_next_proxy()
                    if new_proxy:
                        logger.info(f"Retrying {phone} with proxy {new_proxy}")
                        try:
                            client = self._create_client(phone, new_proxy)
                            await client.connect()
                            if await client.is_user_authorized():
                                clients.append((phone, client))
                                self.config[phone]['proxy'] = new_proxy
                                save_config(self.accounts_json, self.config)
                        except Exception as e2:
                            logger.error(f"Retry failed: {e2}")
        return clients

    async def close_clients(self, clients):
        for _, client in clients:
            try:
                await client.disconnect()
            except:
                pass

# ---------- REPORT ENGINE ----------
async def report_target(client, target, reason, message_ids=None):
    try:
        entity = await client.get_entity(target)
        result = await client(ReportRequest(
            peer=entity,
            id=message_ids or [],
            reason=reason,
            message=""
        ))
        return result is not None
    except errors.FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s")
        await asyncio.sleep(e.seconds + 1)
        return False
    except Exception as e:
        logger.error(f"Report error: {e}")
        return False

async def mass_report(clients, target, reason, message_ids=None, concurrency=10):
    sem = asyncio.Semaphore(concurrency)
    async def worker(phone, client):
        async with sem:
            success = await report_target(client, target, reason, message_ids)
            return phone, success
    tasks = [worker(phone, client) for phone, client in clients]
    results = await asyncio.gather(*tasks)
    success_count = sum(1 for _, s in results if s)
    fail_count = len(results) - success_count
    return success_count, fail_count, results

# ---------- BOT HANDLERS ----------
running_task = None
current_report_info = {}
settings = SettingsManager()

# Start and help
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Telegram Mass Reporter Bot\n"
        "Commands:\n"
        "/addaccount – Add Telegram account\n"
        "/removeaccount – Remove account\n"
        "/listaccounts – List accounts\n"
        "/addproxy <proxy> – Add a single proxy\n"
        "/proxytxt – Upload a .txt file with proxies\n"
        "/listproxies – List all proxies\n"
        "/clearproxies – Remove all proxies\n"
        "/setcycles <num> – Set fixed cycles (0 = random 1-5)\n"
        "/setrandomcycles – Toggle random cycles mode\n"
        "/setconcurrency <num> – Set concurrency\n"
        "/settings – Show current settings\n"
        "/startreport <target> <reason> [msg_ids] – Start report\n"
        "/stopreport – Stop current report\n"
        "/status – Show report status"
    )

# Account addition conversation
ADD_ACCOUNT = range(1)
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send phone number (e.g., +1234567890):")
    return ADD_ACCOUNT

async def add_account_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data['add_phone'] = phone
    await update.message.reply_text("Send API ID (integer):")
    return ADD_ACCOUNT

async def add_account_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        api_id = int(update.message.text.strip())
        context.user_data['add_api_id'] = api_id
        await update.message.reply_text("Send API Hash:")
        return ADD_ACCOUNT
    except:
        await update.message.reply_text("Invalid API ID. Please send an integer.")
        return ADD_ACCOUNT

async def add_account_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api_hash = update.message.text.strip()
    context.user_data['add_api_hash'] = api_hash
    await update.message.reply_text("Send proxy (optional, or type 'skip'):")
    return ADD_ACCOUNT

async def add_account_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proxy = update.message.text.strip()
    if proxy.lower() == 'skip':
        proxy = None
    phone = context.user_data['add_phone']
    api_id = context.user_data['add_api_id']
    api_hash = context.user_data['add_api_hash']
    manager = AccountManager()
    manager.config[phone] = {"api_id": api_id, "api_hash": api_hash, "proxy": proxy}
    save_config(manager.accounts_json, manager.config)
    try:
        client = manager._create_client(phone, proxy)
        await client.connect()
        if await client.is_user_authorized():
            await update.message.reply_text(f"✅ Account {phone} added and authorized.")
        else:
            await update.message.reply_text(f"⚠️ Account {phone} added but NOT authorized. You'll need to login manually via script.")
        await client.disconnect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error adding account: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# Remove account
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /removeaccount <phone>")
        return
    phone = args[0]
    manager = AccountManager()
    if phone in manager.config:
        del manager.config[phone]
        save_config(manager.accounts_json, manager.config)
        session_file = f"{manager.sessions_dir}/{phone}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
        await update.message.reply_text(f"✅ Removed account {phone}")
    else:
        await update.message.reply_text("Account not found.")

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    manager = AccountManager()
    if not manager.config:
        await update.message.reply_text("No accounts saved.")
        return
    lines = ["📋 Saved accounts:"]
    for phone, creds in manager.config.items():
        proxy = creds.get('proxy', 'None')
        lines.append(f"• {phone} (proxy: {proxy})")
    await update.message.reply_text("\n".join(lines))

# Proxy commands
async def add_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addproxy <proxy_string>")
        return
    proxy = ' '.join(args)
    manager = AccountManager()
    if manager.add_proxy(proxy):
        await update.message.reply_text(f"✅ Added proxy: {proxy}")
    else:
        await update.message.reply_text("Proxy already exists.")

async def proxy_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith('.txt'):
        await update.message.reply_text("Please reply with a .txt file containing one proxy per line.")
        return
    file = await context.bot.get_file(document.file_id)
    file_path = f"/tmp/{document.file_name}"
    await file.download_to_drive(file_path)
    try:
        with open(file_path, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        manager = AccountManager()
        added = manager.add_proxies_from_list(proxies)
        await update.message.reply_text(f"✅ Added {added} new proxies from file.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing file: {e}")
    finally:
        os.remove(file_path)

async def list_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    manager = AccountManager()
    proxies = manager.get_proxies()
    if not proxies:
        await update.message.reply_text("No proxies in pool.")
        return
    lines = [f"📋 Proxies ({len(proxies)}):"]
    for i, p in enumerate(proxies[:20], 1):
        lines.append(f"{i}. {p}")
    if len(proxies) > 20:
        lines.append(f"... and {len(proxies)-20} more.")
    await update.message.reply_text("\n".join(lines))

async def clear_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    manager = AccountManager()
    manager.clear_proxies()
    await update.message.reply_text("✅ All proxies cleared.")

# Settings commands
async def set_cycles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setcycles <num>  (0 = random 1-5)")
        return
    try:
        num = int(args[0])
        if num < 0:
            num = 0
        settings.set_fixed_cycles(num)
        if num == 0:
            await update.message.reply_text("✅ Random cycles mode enabled (1-5).")
        else:
            await update.message.reply_text(f"✅ Fixed cycles set to {num}.")
    except:
        await update.message.reply_text("Invalid number.")

async def set_random_cycles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = settings.settings['random_cycles']
    new_val = not current
    settings.set_random_cycles(new_val)
    if new_val:
        await update.message.reply_text("✅ Random cycles mode enabled (1-5).")
    else:
        await update.message.reply_text(f"✅ Random cycles disabled. Using fixed cycles: {settings.settings['fixed_cycles']}.")

async def set_concurrency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setconcurrency <num>")
        return
    try:
        num = int(args[0])
        if num < 1:
            num = 1
        settings.set_concurrency(num)
        await update.message.reply_text(f"✅ Concurrency set to {num}.")
    except:
        await update.message.reply_text("Invalid number.")

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = settings.settings
    cycles_info = f"Random 1-5" if s['random_cycles'] else f"Fixed: {s['fixed_cycles']}"
    text = (f"⚙️ Current Settings:\n"
            f"• Cycles: {cycles_info}\n"
            f"• Concurrency: {s['concurrency']}")
    await update.message.reply_text(text)

# Report control
async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running_task, current_report_info
    if running_task and not running_task.done():
        await update.message.reply_text("⏳ A report is already running. Use /stopreport to stop it first.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /startreport <target> <reason> [msg_ids]\n"
            "target: @username or numeric ID\n"
            "reason: 1=Spam,2=Violence,3=Pornography,4=ChildAbuse,5=Copyright,6=Other\n"
            "msg_ids: optional comma-separated integers"
        )
        return
    target = args[0]
    try:
        reason_code = int(args[1])
    except:
        await update.message.reply_text("Reason must be a number (1-6).")
        return
    reason = REPORT_REASONS.get(reason_code)
    if not reason:
        await update.message.reply_text("Reason not found (1-6).")
        return
    message_ids = []
    if len(args) > 2:
        try:
            message_ids = [int(x) for x in args[2].split(',')]
        except:
            await update.message.reply_text("Message IDs must be comma-separated integers.")
            return
    async def perform_report():
        global current_report_info
        manager = AccountManager()
        clients = await manager.get_all_clients()
        if not clients:
            await update.message.reply_text("❌ No authorized clients available.")
            return
        await update.message.reply_text(f"🚀 Starting mass report on {target} with {len(clients)} clients...")
        concurrency = settings.get_concurrency()
        for cycle in range(settings.get_cycles()):
            success, fail, _ = await mass_report(clients, target, reason, message_ids, concurrency)
            current_report_info = {"target": target, "cycle": cycle + 1, "success": success, "fail": fail}
            await update.message.reply_text(f"📊 Cycle {cycle+1}: {success} success, {fail} failed")
            if cycle < settings.get_cycles() - 1:
                await asyncio.sleep(2)
        await manager.close_clients(clients)
        await update.message.reply_text("✅ Report completed!")
        current_report_info = {}
    running_task = asyncio.create_task(perform_report())

async def stop_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running_task
    if running_task and not running_task.done():
        running_task.cancel()
        await update.message.reply_text("⏹️ Report stopped.")
        running_task = None
    else:
        await update.message.reply_text("No active report.")

async def report_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running_task, current_report_info
    if running_task and not running_task.done():
        if current_report_info:
            info = current_report_info
            await update.message.reply_text(
                f"📊 Report Status:\n"
                f"Target: {info.get('target', 'N/A')}\n"
                f"Cycle: {info.get('cycle', 'N/A')}\n"
                f"Success: {info.get('success', 0)}\n"
                f"Failed: {info.get('fail', 0)}"
            )
        else:
            await update.message.reply_text("⏳ Report running...")
    else:
        await update.message.reply_text("No active report.")

async def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for add_account
    add_account_handler = ConversationHandler(
        entry_points=[CommandHandler("addaccount", add_account_start)],
        states={
            ADD_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_api_id),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_api_hash),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_proxy),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(add_account_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("removeaccount", remove_account))
    application.add_handler(CommandHandler("listaccounts", list_accounts))
    application.add_handler(CommandHandler("addproxy", add_proxy))
    application.add_handler(MessageHandler(filters.Document.TEXT, proxy_txt))
    application.add_handler(CommandHandler("listproxies", list_proxies))
    application.add_handler(CommandHandler("clearproxies", clear_proxies))
    application.add_handler(CommandHandler("setcycles", set_cycles))
    application.add_handler(CommandHandler("setrandomcycles", set_random_cycles))
    application.add_handler(CommandHandler("setconcurrency", set_concurrency))
    application.add_handler(CommandHandler("settings", show_settings))
    application.add_handler(CommandHandler("startreport", start_report))
    application.add_handler(CommandHandler("stopreport", stop_report))
    application.add_handler(CommandHandler("status", report_status))
    
    await application.run_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        # Keep container alive so you can see logs
        import time
        while True:
            time.sleep(10)
