# -*- coding: utf-8 -*-
"""تنظیمات ربات فروش star self — همه از .env / متغیرهای محیطی."""
import os
from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()
        self.bot_token = os.getenv("BOT_TOKEN", "").strip()
        self.admin_id = int(os.getenv("ADMIN_ID", "0") or 0)
        self.api_id = int(os.getenv("API_ID", "0") or 0)
        self.api_hash = os.getenv("API_HASH", "").strip()
        self.shop_key = os.getenv("SHOP_KEY", "").strip() or "change-me-key"
        self.db_path = os.getenv("DB_PATH", "data/star.db")
        self.port = int(os.getenv("PORT", "8080") or 8080)
        self.enc_key = os.getenv("ENCRYPTION_KEY", "").strip()
        self.bot_username = os.getenv("BOT_USERNAME", "st4r_self_bot").strip().lstrip("@")
        self.brand = "star self"

        # اکانت‌های خودت از طریق گیت‌هاب: هر خط یک StringSession (~۳۶۰ حرفی)
        # یک Secret با نام OWNER_SESSIONS بساز؛ ربات هر بار بالا بیاید همگام می‌کند
        self.owner_sessions_raw = os.getenv("OWNER_SESSIONS", "")

        # اختیاری: فعال‌سازی آنی با اجرای workflow سلف روی GitHub Actions (فاز ۲)
        self.gh_repo = os.getenv("GH_REPO", "").strip()          # owner/repo
        self.gh_token = os.getenv("GH_TOKEN", "").strip()
        self.gh_workflow = os.getenv("GH_WORKFLOW", "selfbot.yml").strip()

    def validate(self):
        """فهرست متغیرهای ناقص را برمی‌گرداند؛ خالی یعنی همه‌چیز آماده است."""
        problems = []
        if not self.bot_token:
            problems.append("BOT_TOKEN")
        if not self.admin_id:
            problems.append("ADMIN_ID")
        if not self.api_id or not self.api_hash:
            problems.append("API_ID/API_HASH (برای ساخت سشن مشتری‌ها)")
        if not self.shop_key or self.shop_key == "change-me-key":
            problems.append("SHOP_KEY (کلید API — بدون آن سشن‌ها تحویل داده نمی‌شوند)")
        return problems
