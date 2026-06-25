import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

# Proxy settings
USE_PROXY = True  # Set to True to use proxies from proxies.txt
PROXY_LIST_FILE = "proxies.txt"

# Crownit URLs
CROWNIT_BASE_URL = "https://feedback.crownit.in"
CROWNIT_ONBOARDING_URL = f"{CROWNIT_BASE_URL}/lite/onboarding"
CROWNIT_LOGIN_URL = f"{CROWNIT_BASE_URL}/lite/login"
CROWNIT_SURVEY_URL = f"{CROWNIT_BASE_URL}/lite/survey"
CROWNIT_REWARDS_URL = f"{CROWNIT_BASE_URL}/lite/rewards"

# Database file
DB_FILE = "crownit_bot.db"
