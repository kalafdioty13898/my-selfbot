# -*- coding: utf-8 -*-
"""نقطه ورود سلف‌بوت — پشتیبانی چند اکانت روی GitHub Actions."""
import asyncio
import logging
import os
import sys

from telethon import TelegramClient, events
from telethon.errors import AuthKeyUnregisteredError, UserDeactivatedBanError
from telethon.sessions import StringSession

from config import Config
from framework import Bot, Ctx
from storage import Store
from utils import AdminCache

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logging.getLogger("telethon").setLevel(logging.WARNING)
log = logging.getLogger("selfbot")

TICK_INTERVAL = 20


def build_account(client, store, cfg, key):
    bot = Bot()
    ctx = Ctx(client, store, cfg, key)
    ctx.admins = AdminCache()

    import modules  # noqa: E402 — همه ماژول‌ها خودشان register می‌کنند
    for mod in modules.MODULES:
        mod(bot)

    @client.on(events.NewMessage())
    async def _on_new(event):
        await bot.dispatch(event, ctx)

    @client.on(events.MessageEdited())
    async def _on_edit(event):
        for h in bot.edit_hooks:
            try:
                await h(event, ctx)
            except Exception:
                log.exception("edit hook error")

    @client.on(events.MessageDeleted())
    async def _on_del(event):
        for h in bot.delete_hooks:
            try:
                await h(event, ctx)
            except Exception:
                log.exception("delete hook error")

    @client.on(events.ChatAction())
    async def _on_action(event):
        for h in bot.action_hooks:
            try:
                await h(event, ctx)
            except Exception:
                log.exception("action hook error")

    @client.on(events.CallbackQuery())
    async def _on_cb(event):
        await bot.callback(event, ctx)

    async def _ticker():
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            await bot.tick(ctx)

    return bot, ctx, _ticker


async def main():
    cfg = Config()
    store = Store(cfg)
    os.makedirs("data", exist_ok=True)

    accounts = []
    for i, s in enumerate(cfg.sessions, 1):
        client = TelegramClient(
            StringSession(s), cfg.api_id, cfg.api_hash,
            device_model="Desktop", system_version="Windows 10",
            app_version="MySelf 1.0",
        )
        accounts.append((i, client))

    # اتصال و اعتبارسنجی
    alive = []
    for i, client in accounts:
        try:
            await client.connect()
            if not await client.is_user_authorized():
                log.error("اکانت #%d: سشن نامعتبر است — StringSession را دوباره بساز", i)
                await client.disconnect()
                continue
            alive.append((i, client))
            log.info("اکانت #%d متصل شد ✅", i)
        except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
            log.error("اکانت #%d مشکل سشن/بن: %s", i, e)
        except Exception as e:
            log.error("اکانت #%d اتصال نشد: %s", i, e)

    if not alive:
        log.critical("هیچ اکانتی وصل نشد! سشن‌ها را بررسی کن.")
        sys.exit(1)

    store.client = alive[0][1]
    await store.load()
    log.info("پایگاه داده بارگذاری شد (%d اکانت ثبت‌شده)", len(store.accs()))

    tasks = []
    for i, client in alive:
        bot, ctx, ticker = build_account(client, store, cfg, i)
        await ctx.init()
        log.info("اکانت #%d آماده است: %s (id=%s)", i,
                 (ctx.me.first_name or ""), ctx.me_id)
        tasks.append(asyncio.create_task(ticker()))
        tasks.append(client.run_until_disconnected())

    try:
        await asyncio.gather(*tasks)
    finally:
        await store.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
