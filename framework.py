# -*- coding: utf-8 -*-
"""فریم‌ورک کوچک سلف: ثبت دستور/هوک‌ها، مجوزها، ارسال امن."""
import asyncio
import logging
import time

from telethon.errors import FloodWaitError

log = logging.getLogger("selfbot")


class Ctx:
    """زمینه هر اکانت."""

    def __init__(self, client, store, cfg, key):
        self.client = client
        self.store = store
        self.cfg = cfg
        self.key = str(key)
        self.me = None
        self.me_id = 0
        self.started = time.time()
        self.last_activity = time.time()
        self.admins = None  # AdminCache (بعداً ست می‌شود)
        self.extra = {}     # حافظه موقت ماژول‌ها

    @property
    def acc(self):
        return self.store.acc(self.key)

    async def init(self):
        self.me = await self.client.get_me()
        self.me_id = self.me.id

    def sudo_ids(self):
        ids = {self.me_id}
        for s in (self.cfg.sudo or "").split(","):
            s = s.strip()
            if s.isdigit():
                ids.add(int(s))
        return ids

    def is_sudo(self, uid):
        return uid in self.sudo_ids()

    async def send(self, chat, text=None, **kw):
        try:
            kw.setdefault("link_preview", False)
            return await self.client.send_message(chat, text, **kw)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            return await self.send(chat, text, **kw)
        except Exception as e:
            log.warning("send failed: %s", e)
            return None

    async def reply(self, event, text=None, **kw):
        try:
            kw.setdefault("link_preview", False)
            return await event.reply(text, **kw)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            return await self.reply(event, text, **kw)
        except Exception as e:
            log.warning("reply failed: %s", e)
            return None

    def relay_chat(self):
        """چت پیش‌فرض ذخیره: کانال storage یا پیام‌های ذخیره‌شده."""
        return self.store.cfg.storage_id or "me"


class Bot:
    """رجیستری دستورها و هوک‌ها برای هر اکانت."""

    def __init__(self):
        self.cmds = []          # (aliases, fn, always, cat, help)
        self._order = None      # ترتیب تطبیق (دستورهای طولانی‌تر اول)
        self.msg_hooks = []     # (event, ctx)
        self.out_hooks = []
        self.edit_hooks = []
        self.delete_hooks = []
        self.action_hooks = []
        self.tick_hooks = []
        self.cb_hooks = []      # دکمه‌های شیشه‌ای (CallbackQuery)

    def cmd(self, *aliases, always=False, cat="عمومی", help=None):
        def deco(fn):
            self.cmds.append((list(aliases), fn, always, cat, help))
            return fn
        return deco

    def msg_hook(self, fn):
        self.msg_hooks.append(fn)
        return fn

    def out_hook(self, fn):
        self.out_hooks.append(fn)
        return fn

    def edit_hook(self, fn):
        self.edit_hooks.append(fn)
        return fn

    def delete_hook(self, fn):
        self.delete_hooks.append(fn)
        return fn

    def action_hook(self, fn):
        self.action_hooks.append(fn)
        return fn

    def tick_hook(self, fn):
        self.tick_hooks.append(fn)
        return fn

    def cb_hook(self, fn):
        self.cb_hooks.append(fn)
        return fn

    def match_order(self):
        """دستورهای طولانی‌تر اول چک شوند تا «ذخیره زماندار روشن»
        قربانی تطبیق پیشوندی «ذخیره» نشود (باگ اولویت)."""
        if self._order is None:
            self._order = sorted(self.cmds, key=lambda c: -max(len(a) for a in c[0]))
        return self._order

    async def dispatch(self, event, ctx):
        from utils import match_cmd
        msg = event.message
        text = (msg.raw_text or "").strip()

        # هوک‌های پیام (کش، مدریشن، منشی، ...) — برای همه پیام‌ها حتی مدیای بدون متن
        for h in self.msg_hooks:
            try:
                await h(event, ctx)
            except Exception:
                log.exception("msg hook error")

        # فقط sudo یا خودم
        if not (msg.out or ctx.is_sudo(msg.sender_id or 0)):
            return
        if msg.out:
            ctx.last_activity = time.time()
            for h in self.out_hooks:
                try:
                    await h(event, ctx)
                except Exception:
                    log.exception("out hook error")

        # دستورها فقط متنی‌اند؛ مدیای بدون متن همین‌جا تمام می‌شود (بعد از هوک‌ها)
        if not text:
            return

        chat_id = event.chat_id
        acc = ctx.acc
        for aliases, fn, always, _, _ in self.match_order():
            arg = None
            for a in aliases:
                arg = match_cmd(text, a, ctx.cfg.prefix)
                if arg is not None:
                    break
            if arg is None:
                continue
            # گیت خاموش/روشن
            if not always:
                if acc["off"]["all"] and not msg.out:
                    return
                if (acc["off"]["all"] or acc["off"]["chats"].get(str(chat_id))) and a not in (
                        "سلف روشن", "سلف همگانی روشن"):
                    return
            try:
                await fn(event, ctx, arg)
            except FloodWaitError as e:
                await ctx.reply(event, f"⏳ محدودیت تلگرام: {e.seconds} ثانیه صبر کن")
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                log.exception("cmd error: %s", aliases[0])
                await ctx.reply(event, "⚠️ خطایی رخ داد — جزئیات در لاگ")
            return

    async def tick(self, ctx):
        for h in self.tick_hooks:
            try:
                await h(ctx)
            except Exception:
                log.exception("tick hook error")

    async def callback(self, event, ctx):
        for h in self.cb_hooks:
            try:
                await h(event, ctx)
            except Exception:
                log.exception("cb hook error")
