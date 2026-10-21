# -*- coding: utf-8 -*-
"""ماژول ابری: ذخیره/دریافت محتوا با اسم دلخواه (در کانال storage)."""
from framework import Bot


def setup(bot: Bot):
    @bot.cmd("ذخیره محتوا", "csave", cat="ابری",
             help="ذخیره محتوا <اسم> (ریپلی) — هر محتوایی با اسم ذخیره کن")
    async def _save(event, ctx, args):
        name = (args or "").strip().lower()
        if not name:
            return await ctx.reply(event, "❗ اسم بده: ذخیره محتوا اهنگ خفن (با ریپلی)")
        if not event.is_reply:
            return await ctx.reply(event, "❗ روی پیام موردنظر ریپلی کن")
        src = await event.get_reply_message()
        dest = ctx.relay_chat()
        try:
            if src.media:
                fwd = await ctx.client.forward_messages(dest, event.chat_id, src.id)
                kind = "media"
            else:
                fwd = await ctx.client.send_message(dest, src.raw_text or "")
                kind = "text"
        except Exception:
            return await ctx.reply(event, "❌ ارسال به چت ذخیره ناموفق بود (STORAGE_ID را چک کن)")
        ctx.acc["cloud"][name] = {"chat": dest, "msg": fwd.id, "kind": kind}
        ctx.store.save()
        await ctx.reply(event, f"☁️ «{name}» ذخیره شد")

    @bot.cmd("دریافت محتوا", "cget", cat="ابری",
             help="دریافت محتوا <اسم> — محتوای ذخیره‌شده بیاید")
    async def _get(event, ctx, args):
        name = (args or "").strip().lower()
        item = ctx.acc["cloud"].get(name)
        if not item:
            return await ctx.reply(event, "❗ چنین اسمی ذخیره نشده (لیست: لیست ذخیره)")
        try:
            if item["kind"] == "media":
                await ctx.client.forward_messages(event.chat_id, item["chat"], item["msg"])
            else:
                m = await ctx.client.get_messages(item["chat"], ids=[item["msg"]])
                await ctx.reply(event, (m[0].raw_text if m and m[0] else "—"))
        except Exception:
            await ctx.reply(event, "❌ دریافت ناموفق بود (ممکنه از چت ذخیره حذف شده باشه)")

    @bot.cmd("حذف محتوا", "cdel", cat="ابری",
             help="حذف محتوا <اسم> — حذف از حافظه ابری")
    async def _del(event, ctx, args):
        name = (args or "").strip().lower()
        item = ctx.acc["cloud"].pop(name, None)
        if not item:
            return await ctx.reply(event, "❗ چنین اسمی نیست")
        try:
            await ctx.client.delete_messages(item["chat"], [item["msg"]])
        except Exception:
            pass
        ctx.store.save()
        await ctx.reply(event, "✅ حذف شد")

    @bot.cmd("لیست ذخیره", "clist", cat="ابری",
             help="لیست ذخیره — نمایش همه محتواهای ابری")
    async def _list(event, ctx, args):
        c = ctx.acc["cloud"]
        if not c:
            return await ctx.reply(event, "ℹ️ حافظه ابری خالیه")
        await ctx.reply(event, "☁️ محتواهای ذخیره‌شده:\n• " + "\n• ".join(c.keys()))

    @bot.cmd("پاکسازی ذخیره", "cclean", cat="ابری",
             help="پاکسازی ذخیره — پاک کردن کل حافظه ابری")
    async def _clean(event, ctx, args):
        ctx.acc["cloud"] = {}
        ctx.store.save()
        await ctx.reply(event, "♻️ حافظه ابری پاک شد")
