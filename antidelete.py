# -*- coding: utf-8 -*-
"""ماژول آنتی‌حذف: بازیابی پیام‌های حذف/ویرایش‌شده از کش."""
import logging
import os
import time
from collections import OrderedDict

from telethon import events, functions

from framework import Bot
from utils import tmp_path

log = logging.getLogger("selfbot")
CACHE_MAX = 3000
MEDIA_KEEP = 15 * 1024 * 1024  # مدیای تا ۱۵ مگ برای بازیابی


def setup(bot: Bot):
    cache = OrderedDict()  # msg_id -> dict(chat, text, path, sender)

    async def remember(msg, event):
        if not msg:
            return
        try:
            if msg.id in cache:
                cache.move_to_end(msg.id)
            item = {"chat": event.chat_id, "text": msg.raw_text or "",
                    "path": None, "sender": msg.sender_id}
            # مدیای کوچک را دانلود می‌کنیم تا بعد از حذف قابل ارسال باشد
            if msg.media and item["chat"] is not None:
                size = msg.file.size if msg.file else 0
                if size and size <= MEDIA_KEEP:
                    try:
                        item["path"] = await msg.download_media(file=tmp_path("ad"))
                    except Exception:
                        pass
            cache[msg.id] = item
            while len(cache) > CACHE_MAX:
                _, old = cache.popitem(last=False)
                if old.get("path"):
                    try:
                        os.remove(old["path"])
                    except Exception:
                        pass
        except Exception:
            pass

    def relay(ctx):
        return ctx.acc["ad"]["relay"] or ctx.relay_chat()

    @bot.cmd("ذخیره حذف روشن", "adon", cat="آنتی‌حذف",
             help="ذخیره حذف روشن — پیام‌های حذف‌شده به چت ریلم ارسال شود")
    async def _ad_on(event, ctx, args):
        ctx.acc["ad"]["del"] = True
        ctx.store.save()
        await ctx.reply(event, "✅ آنتی‌حذف روشن شد")

    @bot.cmd("ذخیره حذف خاموش", "adoff", cat="آنتی‌حذف",
             help="ذخیره حذف خاموش — غیرفعال کردن آنتی‌حذف")
    async def _ad_off(event, ctx, args):
        ctx.acc["ad"]["del"] = False
        ctx.store.save()
        await ctx.reply(event, "✅ آنتی‌حذف خاموش شد")

    @bot.cmd("ذخیره ویرایش روشن", "edon", cat="آنتی‌حذف",
             help="ذخیره ویرایش روشن — پیام‌های ویرایش‌شده گزارش شود")
    async def _ed_on(event, ctx, args):
        ctx.acc["ad"]["edit"] = True
        ctx.store.save()
        await ctx.reply(event, "✅ ذخیره ویرایش‌ها روشن شد")

    @bot.cmd("ذخیره ویرایش خاموش", "edoff", cat="آنتی‌حذف",
             help="ذخیره ویرایش خاموش — غیرفعال کردن گزارش ویرایش")
    async def _ed_off(event, ctx, args):
        ctx.acc["ad"]["edit"] = False
        ctx.store.save()
        await ctx.reply(event, "✅ ذخیره ویرایش‌ها خاموش شد")

    @bot.cmd("تنظیم ریلم", "setrelay", cat="آنتی‌حذف",
             help="تنظیم ریلم — در چتی که هستی، مقصد ذخیره حذف/ویرایش شود")
    async def _set_relay(event, ctx, args):
        ctx.acc["ad"]["relay"] = event.chat_id
        ctx.store.save()
        await ctx.reply(event, "✅ این چت به عنوان مقصد آنتی‌حذف تنظیم شد")

    # ---------- هوک‌ها ----------
    @bot.msg_hook
    async def _cache_msg(event, ctx):
        await remember(event.message, event)

    @bot.delete_hook
    async def _on_delete(event, ctx):
        if not ctx.acc["ad"]["del"]:
            return
        ids = event.deleted_ids or []
        found = []
        for i in ids:
            item = cache.pop(i, None)
            if item:
                found.append(item)
        if not found:
            return
        dest = relay(ctx)
        for item in found[:10]:
            try:
                who = f"<code>{item['sender']}</code>" if item.get("sender") else "نامشخص"
                cap = (f"🗑 <b>پیام حذف‌شده</b>\n👤 ارسال‌کننده: {who}\n"
                       f"💬 چت: <code>{item['chat']}</code>")
                if item.get("path") and os.path.exists(item["path"]):
                    await ctx.client.send_file(dest, item["path"], caption=cap,
                                               parse_mode="html")
                    os.remove(item["path"])
                elif item.get("text"):
                    await ctx.client.send_message(dest, cap + "\n\n📝 " + item["text"],
                                                  parse_mode="html")
            except Exception:
                log.exception("anti-delete relay failed")

    @bot.edit_hook
    async def _on_edit(event, ctx):
        if not ctx.acc["ad"]["edit"]:
            return
        msg = event.message
        old = cache.get(msg.id)
        if not old:
            return
        new_text = msg.raw_text or ""
        if (old.get("text") or "") == new_text:
            return
        try:
            await ctx.client.send_message(
                relay(ctx),
                f"✏️ <b>پیام ویرایش شد</b>\n👤 <code>{msg.sender_id}</code>\n"
                f"💬 چت: <code>{event.chat_id}</code>\n\n"
                f"<b>قبل:</b> {old.get('text') or '—'}\n\n<b>بعد:</b> {new_text}",
                parse_mode="html")
        except Exception:
            pass
        old["text"] = new_text

    @bot.tick_hook
    async def _cleanup(ctx):
        # پاک‌سازی فایل‌های موقت قدیمی
        d = os.path.join(os.getcwd(), "tmp_dl")
        if os.path.isdir(d):
            for f in os.listdir(d):
                p = os.path.join(d, f)
                try:
                    if time.time() - os.path.getmtime(p) > 3600:
                        os.remove(p)
                except Exception:
                    pass
        # بستن فاصله حافظه: پیام‌های قدیمی کش بدون فایل حذف شوند
        while len(cache) > CACHE_MAX:
            _, old = cache.popitem(last=False)
            if old.get("path"):
                try:
                    os.remove(old["path"])
                except Exception:
                    pass
