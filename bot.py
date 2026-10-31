# -*- coding: utf-8 -*-
"""نقطه ورود سلف‌بوت — پشتیبانی چند اکانت روی GitHub Actions."""
import asyncio
import collections
import logging
import os
import signal
import sys
import time

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
MAX_DYNAMIC = 25  # سقف اکانت‌های مشتری‌های فروشگاه در هر ران


async def warm_entity_cache(client, label="?"):
    """کش اِنتیتی StringSession بعد از هر ری‌استارت Actions خالی است؛
    هر چتی که با آیدی عددی (-100...) در تنظیمات ذخیره شده (قفل گروه، مقصد
    سیو چنل/ذخیره خودکار، ست لاگ، ...) بدون این گرم‌سازی get_entity نمی‌شود
    و قابلیت‌ها ساکت از کار می‌افتند. یک get_dialogs کش را پر می‌کند."""
    try:
        await client.get_dialogs(limit=300)
        log.info("کش گفتگوهای اکانت %s گرم شد ✅", label)
    except Exception as e:
        log.warning("گرم‌سازی کش اکانت %s ناموفق: %s", label, e)


class DynamicPool:
    """اکانت‌های مشتری‌های فروشگاه star self — استارت/استاپ زنده بدون ری‌استارت.

    فروشگاه بعد از هر خرید star.db را پوش می‌کند؛ ShopSync سشن جدید را
    می‌دهد و اینجا همان لحظه کلاینتش بالا می‌آید (≤ ۲ دقیقه بعد از خرید).
    """

    def __init__(self, cfg, store):
        self.cfg = cfg
        self.store = store
        self.units = {}     # uid -> {client, ctx, tick, mon, since}
        self.warm = []      # تسک‌های گرم‌سازی کش (رفرنس نگه‌داری)
        self.dead = asyncio.Queue()  # uid هایی که کلاینت‌شان ناگهانی مرد
        self.sessions = {}  # uid -> آخرین سشن شناخته‌شده (برای ری‌استارت دستی مدیر)
        self.blocked = set()  # uid هایی که مدیر استاپ کرده — sync دوباره استارت‌شان نمی‌کند
        self._seq = 1000
        # خودثبت برای پنل مدیر (modules/boss_mod.py) — بدون import چرخشی
        try:
            store.pool = self
        except Exception:
            pass

    def _buyer_cfg(self):
        import copy
        c = copy.copy(self.cfg)
        c.sudo = ""  # حریم خصوصی: فقط خود مشتری روی سلفتش کنترل دارد
        return c

    async def start(self, uid: str, session: str) -> bool:
        uid = str(uid)
        if uid in self.blocked:
            log.info("مشتری %s در لیست مسدود مدیر است — استارت نشد", uid)
            return False
        if uid in self.units:
            # سشن این uid عوض شده — قدیمی را قطع کن و از نو بساز
            await self.stop(uid)
        if len(self.units) >= MAX_DYNAMIC:
            log.warning("ظرفیت داینامیک پر است (%d) — %s رد شد", MAX_DYNAMIC, uid)
            return False
        client = TelegramClient(
            StringSession(session), self.cfg.api_id, self.cfg.api_hash,
            device_model="Desktop", system_version="Windows 10",
            app_version="Star Self 1.0",
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False
        except Exception as e:
            log.warning("کلاینت مشتری %s وصل نشد: %s", uid, e)
            try:
                await client.disconnect()
            except Exception:
                pass
            return False
        try:
            n = self._seq
            self._seq += 1
            bot, ctx, ticker = build_account(client, self.store, self._buyer_cfg(), f"u{uid}")
            await ctx.init()
            ctx.buyer_uid = uid
            # تله‌متری دستورها — فقط دستورهایی که به سلفِ خودش می‌زند (نه چت‌هایش)
            ctx.extra["cmdlog"] = collections.deque(maxlen=40)
            tick_task = asyncio.create_task(ticker())
            unit = {"client": client, "ctx": ctx, "tick": tick_task,
                    "mon": None, "since": time.time()}
            self.units[uid] = unit
            self.sessions[uid] = session

            async def _monitor():
                """مرگ غیرمنتظره کلاینت (بن/قطعی) → از پول خارج + گزارش به ShopSync."""
                try:
                    await client.run_until_disconnected()
                except Exception:
                    pass
                cur = self.units.get(uid)
                if cur and cur["client"] is client:  # نه از مسیر stop() دستی
                    self.units.pop(uid, None)
                    if cur["tick"]:
                        cur["tick"].cancel()
                    try:
                        self.dead.put_nowait(uid)
                    except Exception:
                        pass
                    log.warning("کلاینت مشتری %s قطع شد — بعد از پول بعدی دوباره استارت می‌شود", uid)

            mon_task = asyncio.create_task(_monitor())
            unit["mon"] = mon_task
            log.info("🛒 اکانت مشتری %s آماده شد: %s (id=%s)",
                     uid, (ctx.me.first_name or ""), ctx.me_id)
            # گرم‌سازی کش — مقصدهای عددیِ تنظیمات بعد از ری‌استارت resolve نشدنی‌اند
            self.warm.append(asyncio.create_task(warm_entity_cache(client, f"buyer:{uid}")))
            return True
        except Exception:
            log.exception("setup buyer %s failed", uid)
            try:
                await client.disconnect()
            except Exception:
                pass
            self.units.pop(uid, None)
            return False

    async def stop(self, uid: str):
        uid = str(uid)
        unit = self.units.pop(uid, None)
        if not unit:
            return
        client = unit["client"]
        tasks = [unit["tick"], unit["mon"]]
        for t in tasks:  # (ticker, monitor)
            if t:
                t.cancel()
        try:
            await client.disconnect()
        except Exception:
            pass
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*[t for t in tasks if t], return_exceptions=True), 10)
            except Exception:
                pass
        log.info("اکانت مشتری %s قطع شد", uid)

    async def restart(self, uid: str) -> bool:
        """ری‌استارت از آخرین سشن شناخته‌شده (برای پنل مدیر)."""
        uid = str(uid)
        s = self.sessions.get(uid)
        if not s:
            return False
        await self.stop(uid)
        return await self.start(uid, s)

    async def stop_all(self):
        for uid in list(self.units.keys()):
            await self.stop(uid)


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
            app_version="Star Self 1.0",
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
    warm_tasks = []
    for i, client in alive:
        bot, ctx, ticker = build_account(client, store, cfg, i)
        await ctx.init()
        log.info("اکانت #%d آماده است: %s (id=%s)", i,
                 (ctx.me.first_name or ""), ctx.me_id)
        tasks.append(asyncio.create_task(ticker()))
        # ⚠️ پایتون ۳.۱۱+: asyncio.wait coroutine خام قبول نمی‌کند — باید Task باشد
        tasks.append(asyncio.create_task(client.run_until_disconnected()))
        # گرم‌سازی کش گفتگوها (بدون join — جدا از tasks اصلی تا FIRST_COMPLETED
        # با تمام‌شدنش همه‌چیز قطع نشود)
        warm_tasks.append(asyncio.create_task(warm_entity_cache(client, i)))

    # اکانت‌های مشتری‌های فروشگاه star self (فعال‌سازی ≤ ۲ دقیقه بعد از خرید)
    pool = DynamicPool(cfg, store)
    sync = None
    if cfg.enc_key:
        from shop_sync import ShopSync
        sync = ShopSync(cfg, pool.start, pool.stop, dead_queue=pool.dead)
        tasks.append(asyncio.create_task(sync.run()))
    else:
        log.info("SHOP_ENCRYPTION_KEY تنظیم نشده — اتصال به فروشگاه غیرفعال است")

    # GitHub Actions موقع پایان مهلت (timeout) سیگنال SIGTERM می‌فرستد؛
    # بدون این هندلر، پروسه بدون flush کشته می‌شد و آخرین تنظیمات گم می‌شد.
    stop_evt = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_evt.set)
        except (NotImplementedError, RuntimeError):
            pass
    stop_task = asyncio.create_task(stop_evt.wait())
    tasks.append(stop_task)

    try:
        # FIRST_COMPLETED: با SIGTERM (یا مرگ یک کلاینت) بقیه لغو و flush انجام شود —
        # قبلاً gather بود و تا مرگ همه taskها منتظر می‌ماند (flush هرگز اجرا نمی‌شد)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        # flush قبل از قطع کلاینت‌ها — آپلود تلگرامی به کلاینت زنده نیاز دارد
        try:
            await store.flush()
        except Exception:
            pass
        try:
            for _, client in alive:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            await pool.stop_all()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
