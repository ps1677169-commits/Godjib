import sqlite3
import json
from datetime import datetime
from config import DB_FILE

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Accounts table (Crownit accounts created by bot)
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT UNIQUE,
            email TEXT,
            password TEXT,
            cookie TEXT,
            token TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_survey TIMESTAMP,
            total_earned REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)
    
    # Surveys completed
    c.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            survey_id TEXT,
            reward REAL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    """)
    
    # Rewards redeemed
    c.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            reward_type TEXT,
            reward_code TEXT,
            reward_link TEXT,
            redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    """)
    
    # OTP requests (pending)
    c.execute("""
        CREATE TABLE IF NOT EXISTS otp_requests (
            phone TEXT PRIMARY KEY,
            request_id TEXT,
            expires_at TIMESTAMP,
            user_id INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

# ============ User functions ============
def get_or_create_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        conn.commit()
    conn.close()
    return user

def get_user_phone(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_user_phone(user_id, phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    conn.commit()
    conn.close()

# ============ Account functions ============
def create_account(user_id, phone, email, password, cookie=None, token=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO accounts (user_id, phone, email, password, cookie, token, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
    """, (user_id, phone, email, password, cookie, token))
    account_id = c.lastrowid
    conn.commit()
    conn.close()
    return account_id

def get_account(account_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_accounts_by_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_account_status(account_id, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, account_id))
    conn.commit()
    conn.close()

def update_account_cookie(account_id, cookie, token=None):
    conn = get_db()
    c = conn.cursor()
    if token:
        c.execute("UPDATE accounts SET cookie = ?, token = ? WHERE id = ?", (cookie, token, account_id))
    else:
        c.execute("UPDATE accounts SET cookie = ? WHERE id = ?", (cookie, account_id))
    conn.commit()
    conn.close()

# ============ Survey functions ============
def add_survey_completed(account_id, survey_id, reward):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO surveys (account_id, survey_id, reward) VALUES (?, ?, ?)",
        (account_id, survey_id, reward)
    )
    c.execute("UPDATE accounts SET total_earned = total_earned + ? WHERE id = ?", (reward, account_id))
    conn.commit()
    conn.close()

# ============ Reward functions ============
def add_reward(account_id, reward_type, code, link):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO rewards (account_id, reward_type, reward_code, reward_link) VALUES (?, ?, ?, ?)",
        (account_id, reward_type, code, link)
    )
    conn.commit()
    conn.close()

# ============ OTP functions ============
def save_otp_request(phone, request_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO otp_requests (phone, request_id, expires_at, user_id) VALUES (?, ?, datetime('now', '+10 minutes'), ?)",
        (phone, request_id, user_id)
    )
    conn.commit()
    conn.close()

def get_otp_request(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT request_id, user_id FROM otp_requests WHERE phone = ? AND expires_at > datetime('now')", (phone,))
    row = c.fetchone()
    conn.close()
    return row

def delete_otp_request(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM otp_requests WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()