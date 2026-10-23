# -*- coding: utf-8 -*-
"""ربات فروش star self — نقطه ورود.

اجرا:  python bot.py
همراه API سشن‌ها روی PORT (پیش‌فرض 8080) برای اتصال سلف.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import texts as T
from api import build_api
from config import Config
from db import DB
from owner_import import run_owner_import
from handlers import activate, admin, coins, misc, start, tariff, wallet

log = logging.getLogger("star_self")


async def maintenance_loop(db: DB, bot: Bot, cfg: Config):
    """هر ۵ دقیقه: منقضی‌کردن، اخطار ۴۸ ساعته، تمدید خودکار روزانه."""
    while True:
        try:
            n = await db.expire_due()
            if n:
                log.info(f"expired {n} activation(s)")

            # اخطار ۴۸ ساعت قبل از اتمام
            for row in await db.due_for_warn(48):
                try:
                    await bot.send_message(row["user_id"], T.WARN_2D)
                    await db.mark_warned(row["id"])
                    log.info(f"warn sent uid={row['user_id']}")
                except Exception:
                    pass
        except Exception as e:
            log.exception(f"maintenance: {e}")

        # تمدید خودکار با موجودی (فقط پلن سکه‌ای)
        try:
            renew_cost = await db.sint("daily_renew", 3)
            for row in await db.renew_candidates(renew_cost):
                uid = row["user_id"]
                bal = await db.balance(uid)
                if bal < renew_cost:
                    continue
                await db.add_balance(uid, -renew_cost, "renew", "تمدید خودکار روزانه")
                new_exp = await db.extend(uid, 1)
                if not new_exp:
                    # فعال‌سازی بین کوئری و تمدید حذف/منقضی شد — سکه برگردد
                    await db.add_balance(uid, renew_cost, "renew_refund",
                                         "تمدید ناموفق — برگشت سکه")
                    continue
                try:
                    await bot.send_message(uid, T.RENEW_AUTO.format(
                        cost=renew_cost, expires=new_exp[:16],
                        balance=await db.balance(uid)))
                except Exception:
                    pass
                log.info(f"auto-renew uid={uid} -> {new_exp}")
        except Exception as e:
            log.exception(f"renew: {e}")

        await asyncio.sleep(300)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    cfg = Config()
    problems = cfg.validate()
    if problems:
        raise SystemExit("❌ این متغیرها را در .env تنظیم کن: " + ", ".join(problems))

    db = DB(cfg.db_path)
    await db.init(cfg.admin_id)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=None))
    cfg.bot = bot  # برای نوتیف ادمین از داخل هندلرها (رسید خرید و ...)
    try:
        me = await bot.get_me()
        cfg.bot_username = me.username or cfg.bot_username
        log.info(f"🤖 @{cfg.bot_username} | admin={cfg.admin_id}")
    except Exception as e:
        raise SystemExit(f"❌ توکن ربات نامعتبر است: {e}")

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.build(cfg, db))
    dp.include_router(wallet.build(cfg, db))
    dp.include_router(coins.build(cfg, db))
    dp.include_router(activate.build(cfg, db))
    dp.include_router(tariff.build(cfg, db))
    dp.include_router(misc.build(cfg, db))
    dp.include_router(admin.build(cfg, db))

    # API سشن‌ها
    app = build_api(cfg, db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", cfg.port)
    await site.start()
    log.info(f"🌐 API روی پورت {cfg.port} بالا آمد")

    # اکانت‌های خودِ مالک از طریق Secret گیت‌هاب (OWNER_SESSIONS) — همگام‌سازی
    owner_task = asyncio.create_task(run_owner_import(db, cfg))

    asyncio.create_task(maintenance_loop(db, bot, cfg))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
