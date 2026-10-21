# -*- coding: utf-8 -*-
"""ساخت StringSession — روی کامپیوتر خودت اجرا کن (نه گیت‌هاب):
    pip install telethon
    python gen_session.py
خروجی یک کد ~۳۶۰ حرفی است که در GitHub Secrets با نام SESSION (یا SESSION_1) قرار می‌دهی."""
import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("=== ساخت سشن برای سلف‌بوت ===\n")
    api_id = input("API_ID (از my.telegram.org): ").strip()
    api_hash = input("API_HASH: ").strip()

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        me = await client.get_me()
        ss = client.session.save()
        print("\n✅ لاگین شد:", (me.first_name or ""), "| id:", me.id)
        print("\n" + "=" * 50)
        print("سشن تو (این را در GitHub Secrets بگذار):")
        print("=" * 50)
        print(ss)
        print("=" * 50)
        with open("session_string.txt", "w", encoding="utf-8") as f:
            f.write(ss)
        print("\nدر فایل session_string.txt هم ذخیره شد (بعد از استفاده پاکش کن!)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
