import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

PROXY_LIST_FILE = "proxies.txt"
USE_PROXY = False  # Set to True if you have proxies

CROWNIT_BASE_URL = "https://feedback.crownit.in"
CROWNIT_LOGIN_URL = f"{CROWNIT_BASE_URL}/lite/login"
CROWNIT_SURVEY_URL = f"{CROWNIT_BASE_URL}/lite/survey"
CROWNIT_REWARDS_URL = f"{CROWNIT_BASE_URL}/lite/rewards"

SURVEY_TIMEOUT = 300
HUMAN_TYPING_DELAY = (0.05, 0.2)

DB_FILE = "crownit_bot.db"