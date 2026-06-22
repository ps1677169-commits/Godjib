============================================
TELEGRAM MASS REPORTER BOT – Full Deployment Guide
============================================

This bot allows you to mass-report Telegram channels/groups using multiple accounts, with proxy rotation and configurable cycles.

1. FILES NEEDED:
   - bot.py (the main script)
   - requirements.txt (dependencies)
   - Procfile (for Railway)
   - .env (for BOT_TOKEN)

2. DEPLOYMENT ON RAILWAY:
   - Create a new project, upload these files (or connect GitHub).
   - Add a Volume for persistence: mount /app (or specific folders: /app/sessions, /app/accounts_config.json, /app/settings.json, /app/proxies.txt)
   - Set environment variable BOT_TOKEN=your_bot_token.
   - Railway will run "python bot.py" via Procfile.

3. BOT COMMANDS (send to your bot on Telegram):
   /start – Show help
   /addaccount – Interactive add of Telegram account (phone, API ID, hash, optional proxy)
   /removeaccount <phone> – Remove an account
   /listaccounts – List all saved accounts
   /addproxy <proxy> – Add a single proxy (e.g., socks5://user:pass@ip:port)
   /proxytxt – Reply with a .txt file containing proxies (one per line)
   /listproxies – Show proxies in pool
   /clearproxies – Remove all proxies
   /setcycles <num> – Set fixed cycles (0 = random 1-5)
   /setrandomcycles – Toggle random cycles mode (on/off)
   /setconcurrency <num> – Set number of concurrent reports per batch (default 10)
   /settings – Show current settings
   /startreport <target> <reason> [msg_ids] – Start mass report
         target: @username or numeric ID (e.g., @spamchannel or -1001234567890)
         reason: 1=Spam, 2=Violence, 3=Pornography, 4=ChildAbuse, 5=Copyright, 6=Other
         msg_ids: optional comma-separated message IDs to report specifically
   /stopreport – Stop the current report
   /status – Show progress of running report

4. HOW IT WORKS:
   - Each account you add must have valid Telegram API credentials (get from my.telegram.org).
   - The bot logs in using Telethon and saves session files in /sessions.
   - Proxies are used to rotate IPs for each account (if available).
   - When you start a report, the bot uses all active accounts to send reports to Telegram's moderation system.
   - Cycles determine how many times each account reports (random 1-5 by default).
   - Concurrency controls how many reports are sent simultaneously.

5. TIPS:
   - Use fresh, aged accounts for better trust.
   - Mix different report reasons.
   - Use proxies from different countries to avoid detection.
   - For private groups, the accounts must be members.

6. IMPORTANT NOTES:
   - This tool is for educational purposes only. Misuse may violate Telegram's Terms of Service.
   - The author assumes no responsibility for any consequences.

============================================