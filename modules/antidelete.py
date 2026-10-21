# -*- coding: utf-8 -*-
"""ماژول آنتی‌حذف: بازیابی پیام‌های حذف/ویرایش‌شده از کش.
فیلتر گزارش: پیوی همه پیام‌ها؛ گروه/کانال فقط اگر پیام منشن خودت باشد
یا ریپلای به یکی از پیام‌های خودت — بقیه گزارش نمی‌شود."""
import html as _html
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
                    "path": None, "sender": msg.sender_id,
                    "title": getattr(event.chat, "title", None),
                    "mentioned": bool(getattr(msg, "mentioned", False)),
                    "reply_to": msg.reply_to_msg_id}
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

    # ---------- فیلتر گزارش: فقط چیزهایی که به خودت ربط دارد ----------
    TAGS = {"mention": "🔖 <b>منشن تو بود!</b>\n",
            "reply": "↩️ <b>ریپلای به پیام تو بود</b>\n"}

    def _pv(cid):
        """پیوی (و پیام‌های ذخیره‌شده): آیدی مثبت یا نامشخص."""
        return cid is None or cid >= 0

    def _chat_label(cid, title):
        if title:
            return f"{_html.escape(str(title))} (<code>{cid}</code>)"
        return f"<code>{cid}</code>"

    async def _who(ctx, uid):
        """اسم خوانا برای ارسال‌کننده (در زمان گزارش، نه برای هر پیام)."""
        if not uid:
            return "نامشخص"
        try:
            e = await ctx.client.get_entity(uid)
            name = " ".join(x for x in [getattr(e, "first_name", None),
                                        getattr(e, "last_name", None)] if x)
            if getattr(e, "username", None):
                return f"{_html.escape(name)} (@{e.username})" if name else f"@{e.username}"
            return _html.escape(name) if name else f"<code>{uid}</code>"
        except Exception:
            return f"<code>{uid}</code>"

    def _del_reason(item, me_id):
        """چرا این حذف گزارش شود؟ None یعنی ربطی به تو نداشت."""
        if _pv(item.get("chat")):
            return "pv"
        if item.get("mentioned"):
            return "mention"
        rt = item.get("reply_to")
        if rt:
            t = cache.get(rt)
            if t and t.get("sender") == me_id:
                return "reply"
        return None

    async def _edit_reason(msg, event, ctx):
        """همان فیلتر برای ویرایش (با یک fetch کمکی در صورت نیاز)."""
        if _pv(event.chat_id):
            return "pv"
        if getattr(msg, "mentioned", False):
            return "mention"
        rt = msg.reply_to_msg_id
        if rt:
            t = cache.get(rt)
            if t and t.get("sender") == ctx.me_id:
                return "reply"
            try:
                r = await event.get_reply_message()
                if r and (r.out or r.sender_id == ctx.me_id):
                    return "reply"
            except Exception:
                pass
        return None

    @bot.cmd("ذخیره حذف روشن", "adon", cat="آنتی‌حذف",
             help="ذخیره حذف روشن — گزارش حذف فعال شود: پیوی همه؛ گروه‌ها فقط منشن یا ریپلای به پیام خودت")
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
             help="ذخیره ویرایش روشن — گزارش ویرایش با قبل/بعد: پیوی همه؛ گروه‌ها فقط منشن یا ریپلای به خودت")
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
            why = _del_reason(item, ctx.me_id)
            if why is None:
                continue
            try:
                who = await _who(ctx, item.get("sender"))
                tag = TAGS.get(why, "")
                cap = (f"{tag}🗑 <b>پیام حذف‌شده</b>\n"
                       f"👤 ارسال‌کننده: {who}\n"
                       f"💬 چت: {_chat_label(item.get('chat'), item.get('title'))}")
                if item.get("path") and os.path.exists(item["path"]):
                    await ctx.client.send_file(dest, item["path"], caption=cap,
                                               parse_mode="html")
                    os.remove(item["path"])
                elif item.get("text"):
                    await ctx.client.send_message(dest, cap + "\n\n📝 " + _html.escape(item["text"]),
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
        why = await _edit_reason(msg, event, ctx)
        if why is None:
            old["text"] = new_text
            return
        try:
            who = await _who(ctx, msg.sender_id)
            tag = TAGS.get(why, "")
            await ctx.client.send_message(
                relay(ctx),
                f"{tag}✏️ <b>پیام ویرایش شد</b>\n👤 {who}\n"
                f"💬 چت: {_chat_label(event.chat_id, getattr(event.chat, 'title', None))}\n\n"
                f"<b>قبل:</b> {_html.escape(old.get('text') or '—')}\n\n"
                f"<b>بعد:</b> {_html.escape(new_text)}",
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
