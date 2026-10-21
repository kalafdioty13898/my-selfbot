# -*- coding: utf-8 -*-
"""تنظیمات سلف‌بوت — همه از متغیرهای محیطی (GitHub Secrets) خوانده می‌شوند."""
import os


class Config:
    def __init__(self):
        self.api_id = int(os.getenv("API_ID", "0"))
        self.api_hash = os.getenv("API_HASH", "")
        if not self.api_id or not self.api_hash:
            raise SystemExit("❌ API_ID یا API_HASH تنظیم نشده! در GitHub Secrets اضافه کن.")

        # سشن‌ها: یا SESSION (تک اکانت) یا SESSION_1 تا SESSION_8 (چند اکانت)
        self.sessions = []
        single = os.getenv("SESSION", "").strip()
        if single:
            self.sessions.append(single)
        for i in range(1, 9):
            s = os.getenv(f"SESSION_{i}", "").strip()
            if s:
                self.sessions.append(s)
        if not self.sessions:
            raise SystemExit("❌ هیچ سشنی پیدا نشد! SESSION یا SESSION_1 رو در Secrets بذار.")

        # آیدی‌های مدیر (sudo) — با کاما جدا
        self.sudo = os.getenv("SUDO", "")
        # چت ذخیره‌سازی/پایگاه‌داده (کانال خصوصی یا Saved Messages اگه خالی باشه)
        self.storage_id = self._parse_chat(os.getenv("STORAGE_ID", ""))
        # پیشوند دستورات انگلیسی (اگر Secret خالی بود، پیش‌فرض)
        self.prefix = (os.getenv("PREFIX") or "!").strip() or "!"
        # منطقه زمانی (اگر Secret خالی بود، پیش‌فرض تهران)
        self.tz = (os.getenv("TZ_INFO") or "Asia/Tehran").strip() or "Asia/Tehran"
        # فایل کش محلی
        self.db_file = os.getenv("DB_FILE", "data/db.json")

    @staticmethod
    def _parse_chat(v):
        v = (v or "").strip()
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return v if v.startswith("@") else None
