# -*- coding: utf-8 -*-
"""ماژول منشی: ریپلای خودکار پیوی با ۳ حالت (معمولی/هوشمند/افلاین) + لیست سیاه."""
import time

from telethon import events
from telethon.tl import types

from framework import Bot
from utils import render_vars


def setup(bot: Bot):
    last_reply = {}  # user_id -> ts

    @bot.cmd("منشی روشن", "secon", cat="منشی",
             help="منشی روشن — ریپلای خودکار پیوی فعال شود")
    async def _on(event, ctx, args):
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event, "🤖 منشی روشن شد" + ("" if ctx.acc["sec"]["text"] else
                                                    "\n⚠️ هنوز پیامی تنظیم نکردی: روی متن ریپلی کن و بزن «تنظیم منشی»"))

    @bot.cmd("منشی خاموش", "secoff", cat="منشی",
             help="منشی خاموش — ریپلای خودکار خاموش شود")
    async def _off(event, ctx, args):
        ctx.acc["sec"]["on"] = False
        ctx.store.save()
        await ctx.reply(event, "🤖 منشی خاموش شد")

    @bot.cmd("تنظیم منشی", "setsec", cat="منشی",
             help="تنظیم منشی (ریپلی روی متن) — پیام منشی تنظیم شود")
    async def _set(event, ctx, args):
        if args:
            ctx.acc["sec"]["text"] = args
        elif event.is_reply:
            m = await event.get_reply_message()
            ctx.acc["sec"]["text"] = m.raw_text or ""
        else:
            return await ctx.reply(event, "❗ روی متن ریپلی کن یا جلوی دستور بنویس")
        ctx.store.save()
        await ctx.reply(event, "✅ پیام منشی ذخیره شد")

    @bot.cmd("وضعیت منشی", "secstatus", cat="منشی",
             help="وضعیت منشی — پیام و حالت فعلی منشی")
    async def _st(event, ctx, args):
        s = ctx.acc["sec"]
        await ctx.reply(event,
                        f"🤖 منشی: {'✅ روشن' if s['on'] else '❌ خاموش'}\n"
                        f"🧠 حالت: {s['mode']}\n⏳ فاصله جواب: {s['cool']} دقیقه\n"
                        f"😴 آستانه افلاین: {s['offline_min']} دقیقه\n"
                        f"🏷 جواب منشن در گروه: {'✅ روشن' if s.get('tag') else '❌ خاموش'}\n"
                        f"💬 پیام: {s['text'] or '—'}")

    @bot.cmd("منشی هوشمند روشن", "secsmart", cat="منشی",
             help="منشی هوشمند روشن — فقط به بار اولی که پیام می‌دهد جواب بدهد")
    async def _smart(event, ctx, args):
        ctx.acc["sec"]["mode"] = "smart"
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event, "🧠 حالت هوشمند فعال شد (فقط پیام‌دهی جدید جواب می‌گیرند)")

    @bot.cmd("منشی آنی روشن", "secnow", cat="منشی",
             help="منشی آنی روشن — بلافاصله و همیشه به پیوی جواب بدهد (حتی وقتی آنلاینی)")
    async def _now(event, ctx, args):
        ctx.acc["sec"]["mode"] = "all"
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event,
                        "⚡ حالت آنی فعال شد: هر پیام خصوصی فوری جواب می‌گیرد\n"
                        f"⏳ فاصله جواب هر کاربر: {ctx.acc['sec']['cool']} دقیقه "
                        "(تغییر: تنظیم زمان منشی 2)")

    @bot.cmd("منشی افلاین روشن", "secoffon", cat="منشی",
             help="منشی افلاین روشن — بعد از X دقیقه بی‌فعالیتی فعال شود")
    async def _offmode(event, ctx, args):
        ctx.acc["sec"]["mode"] = "offline"
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event,
                        "😴 حالت افلاین فعال شد\n"
                        f"بعد از {ctx.acc['sec']['offline_min']} دقیقه که پیام ندادی، به پیام‌های خصوصی جواب می‌دهد\n"
                        "📏 تغییر آستانه: تنظیم منشی افلاین 10")

    @bot.cmd("تنظیم منشی افلاین", "secoffmin", cat="منشی",
             help="تنظیم منشی افلاین <دقیقه> — آستانه افلاین بودن")
    async def _offmin(event, ctx, args):
        try:
            v = max(1, int(args.strip()))
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: تنظیم منشی افلاین 10")
        ctx.acc["sec"]["offline_min"] = v
        ctx.store.save()
        await ctx.reply(event, f"✅ آستانه افلاین: {v} دقیقه")

    @bot.cmd("تنظیم زمان منشی", "seccool", cat="منشی",
             help="تنظیم زمان منشی <دقیقه> — فاصله جواب به هر کاربر")
    async def _cool(event, ctx, args):
        try:
            v = max(1, int(args.strip()))
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: تنظیم زمان منشی 10")
        ctx.acc["sec"]["cool"] = v
        ctx.store.save()
        await ctx.reply(event, f"✅ فاصله جواب منشی: {v} دقیقه")

    @bot.cmd("منشی تگ روشن", "sectagon", cat="منشی",
             help="منشی تگ روشن — توی گروه‌ها هم وقتی منشنت کنند جواب بدهد")
    async def _tagon(event, ctx, args):
        ctx.acc["sec"]["tag"] = True
        ctx.store.save()
        await ctx.reply(event, "🏷 منشی برای منشن‌های گروه هم روشن شد\n"
                                "(فقط وقتی منشنت کنند جواب می‌دهد — نه هر پیام گروه)")

    @bot.cmd("منشی تگ خاموش", "sectagoff", cat="منشی",
             help="منشی تگ خاموش — جواب منشن در گروه‌ها خاموش شود")
    async def _tagoff(event, ctx, args):
        ctx.acc["sec"]["tag"] = False
        ctx.store.save()
        await ctx.reply(event, "🏷 منشی تگ در گروه‌ها خاموش شد")

    # ---------- لیست سیاه ----------
    async def _add_black(event, ctx, args):
        from utils import get_user
        u = await get_user(ctx.client, event, args)
        if not u:
            return await ctx.reply(event, "❗ کاربر پیدا نشد (ریپلی یا آیدی بده)")
        b = ctx.acc["black"]
        if u.id not in b:
            b.append(u.id)
            ctx.store.save()
        await ctx.reply(event, "⛔ به لیست سیاه اضافه شد")

    async def _del_black(event, ctx, args):
        from utils import get_user
        u = await get_user(ctx.client, event, args)
        if u and u.id in ctx.acc["black"]:
            ctx.acc["black"].remove(u.id)
            ctx.store.save()
        await ctx.reply(event, "✅ از لیست سیاه حذف شد")

    bot.cmd("افزودن سیاه", "blackadd", cat="منشی",
            help="افزودن سیاه <user> — منشی و پاسخ سریع بهش جواب ندهند")(_add_black)
    bot.cmd("حذف سیاه", "blackdel", cat="منشی",
            help="حذف سیاه <user> — خارج کردن از لیست سیاه")(_del_black)
    bot.cmd("لیست سیاه", "blacklist", cat="منشی",
            help="لیست سیاه — نمایش لیست سیاه")(
        lambda event, ctx, args: ctx.reply(
            event, "⛔ لیست سیاه:\n" + "\n".join(f"• <code>{i}</code>" for i in ctx.acc["black"])
            if ctx.acc["black"] else "ℹ️ خالی است"))

    # ---------- هوک پیام خصوصی + منشن گروه ----------
    @bot.msg_hook
    async def _secretary(event, ctx):
        msg = event.message
        if msg.out:
            return
        if ctx.bot_off(event.chat_id):
            return  # سلف خاموش است — منشی هم جواب ندهد (قبلاً نادیده گرفته می‌شد)
        s = ctx.acc["sec"]
        if not s["on"] or not s["text"]:
            return
        private = event.is_private
        if not private:
            # گروه: فقط اگر «منشی تگ روشن» باشد و پیام منشن خودت باشد
            if not s.get("tag"):
                return
            if not getattr(msg, "mentioned", False):
                return
        uid = msg.sender_id
        if not uid or ctx.is_sudo(uid):
            return
        sender = msg.sender
        if not sender or getattr(sender, "bot", False) or isinstance(sender, types.Channel):
            return
        if uid in ctx.acc["black"]:
            return
        # ثبت کاربر دیده‌شده (قبل از ثبت تشخیص بده بار اول است یا نه)
        first_time = str(uid) not in ctx.acc["seen"]
        if first_time:
            ctx.acc["seen"][str(uid)] = int(time.time())
            if len(ctx.acc["seen"]) > 5000:
                oldest = sorted(ctx.acc["seen"].items(), key=lambda x: x[1])[:500]
                for k, _ in oldest:
                    ctx.acc["seen"].pop(k, None)
            ctx.store.save()

        now_ts = time.time()
        if s["mode"] == "smart":
            if not first_time:  # قبلاً جواب گرفته
                return
        elif s["mode"] == "offline":
            idle = now_ts - ctx.last_activity
            if idle < s["offline_min"] * 60:
                return
        # فاصله زمانی جواب
        if now_ts - last_reply.get(uid, 0) < s["cool"] * 60:
            return
        last_reply[uid] = now_ts
        try:
            text = render_vars(s["text"], ctx.cfg.tz, user=sender)
            if private:
                await ctx.client.send_message(uid, text)
            else:
                await event.reply(text)
        except Exception:
            pass
