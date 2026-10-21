# -*- coding: utf-8 -*-
"""ماژول هسته: پنل راهنما، پینگ، وضعیت، روشن/خاموش کردن سلف."""
from framework import Bot
from utils import chunk_text, now, render_vars, to_jalali


def setup(bot: Bot):
    # ---------- پنل راهنما ----------
    @bot.cmd("راهنما", "help", "پنل", always=True, cat="عمومی",
             help="راهنما — نمایش پنل کامل دستورات")
    async def _help(event, ctx, args):
        sections = {}
        for aliases, fn, _always, cat, hlp in bot.cmds:
            if not hlp:
                continue
            sections.setdefault(cat, []).append(hlp)
        if args:
            want = args.strip()
            for cat, lines in sections.items():
                if want in (cat, cat.strip("#")) or want.lower() in (c.lower() for c in _en_cat(cat)):
                    body = f"📘 <b>راهنمای {cat}</b>\n\n" + "\n".join(f"• {l}" for l in lines)
                    for part in chunk_text(body):
                        await ctx.reply(event, part, parse_mode="html")
                    return
            await ctx.reply(event, "❌ چنین بخشی پیدا نشد. فقط «راهنما» بفرست تا کل پنل بیاد.")
            return
        n = now(ctx.cfg.tz)
        jy, jm, jd = to_jalali(n.date())
        head = ("🤖 <b>پنل سلف‌بوت شخصی</b>\n"
                f"👤 {(ctx.me.first_name or '')} | 🕐 {n.strftime('%H:%M')} | "
                f"📅 {jy}/{jm:02d}/{jd:02d}\n"
                f"{'─' * 28}\n")
        body = ""
        for cat, lines in sections.items():
            body += f"\n<b>📌 {cat}</b>\n" + "\n".join(f"• {l}" for l in lines) + "\n"
        body += ("\n<i>دستورهای انگلیسی با «" + ctx.cfg.prefix + "» شروع می‌شوند، فارسی‌ها بدون پیشوند.\n"
                 "در هر بخش متن‌ها از متغیرهای TIME, DATE, RANDNUM1-99, NAME, USERNAME پشتیبانی می‌کنند.</i>")
        for part in chunk_text(head + body):
            await ctx.reply(event, part, parse_mode="html")

    def _en_cat(cat):
        m = {"عمومی": ["عمومی", "core"], "مدیا": ["مدیا", "media"],
             "آنتی‌حذف": ["antidelete"], "منشی": ["secretary"],
             "پاسخ سریع": ["quick"], "پروفایل": ["profile"],
             "گروه": ["group"], "یادآور": ["reminder"],
             "ترجمه": ["translate"], "ابری": ["cloud"]}
        return m.get(cat, [cat])

    # ---------- پینگ ----------
    @bot.cmd("پینگ", "ping", always=True, cat="عمومی", help="پینگ — سرعت پاسخ ربات")
    async def _ping(event, ctx, args):
        import time as t
        m = await ctx.reply(event, "⚡ ...")
        ms = int((t.time() - (m.date.timestamp() if m and m.date else t.time())) * 1000)
        up = int(t.time() - ctx.started)
        await ctx.client.edit_message(event.chat_id, m.id,
                                      f"⚡ پینگ: {ms}ms | ⏱ فعال از {up // 3600}س {up % 3600 // 60}د")

    # ---------- وضعیت ----------
    @bot.cmd("وضعیت", "status", always=True, cat="عمومی", help="وضعیت — گزارش کامل سلف")
    async def _status(event, ctx, args):
        acc = ctx.acc
        up = int(now(ctx.cfg.tz).timestamp() - ctx.started)
        txt = (f"📊 <b>وضعیت سلف</b>\n"
               f"👤 اکانت: {(ctx.me.first_name or '')} (<code>{ctx.me_id}</code>)\n"
               f"⏱ فعال بودن: {up // 3600} ساعت و {up % 3600 // 60} دقیقه\n"
               f"🔌 وضعیت: {'🔴 خاموش (همگانی)' if acc['off']['all'] else '🟢 روشن'}\n"
               f"⚡ پاسخ سریع: {len(acc['quick'])} عدد\n"
               f"☁️ ذخیره ابری: {len(acc['cloud'])} عدد\n"
               f"⏰ یادآور فعال: {len(acc['rems'])} | هشدار روزانه: {len(acc['daily'])}\n"
               f"👤 اسم‌های چرخشی: {len(acc['names'])} ({'روشن' if acc['names_on'] else 'خاموش'})\n"
               f"📝 بیوهای چرخشی: {len(acc['bios'])} ({'روشن' if acc['bios_on'] else 'خاموش'})\n"
               f"🤖 منشی: {'✅' if acc['sec']['on'] else '❌'} (حالت {acc['sec']['mode']})\n"
               f"🛡 آنتی‌حذف: {'✅' if acc['ad']['del'] else '❌'}")
        await ctx.reply(event, txt, parse_mode="html")

    # ---------- خاموش/روشن ----------
    @bot.cmd("سلف خاموش", "off", always=True, cat="عمومی",
             help="سلف خاموش — سلف فقط در این چت خاموش می‌شود")
    async def _off(event, ctx, args):
        ctx.acc["off"]["chats"][str(event.chat_id)] = True
        ctx.store.save()
        await ctx.reply(event, "🔴 سلف در این چت خاموش شد (برای همه به‌جز دستورهای اصلی)")

    @bot.cmd("سلف روشن", "on", always=True, cat="عمومی",
             help="سلف روشن — روشن کردن سلف در این چت")
    async def _on(event, ctx, args):
        ctx.acc["off"]["chats"].pop(str(event.chat_id), None)
        ctx.store.save()
        await ctx.reply(event, "🟢 سلف در این چت روشن شد")

    @bot.cmd("سلف همگانی خاموش", "alloff", always=True, cat="عمومی",
             help="سلف همگانی خاموش — سلف در همه‌جا خاموش می‌شود")
    async def _alloff(event, ctx, args):
        ctx.acc["off"]["all"] = True
        ctx.store.save()
        await ctx.reply(event, "🔴 سلف در همه چت‌ها خاموش شد")

    @bot.cmd("سلف همگانی روشن", "allon", always=True, cat="عمومی",
             help="سلف همگانی روشن — روشن کردن سلف در همه‌جا")
    async def _allon(event, ctx, args):
        ctx.acc["off"]["all"] = False
        ctx.store.save()
        await ctx.reply(event, "🟢 سلف در همه‌جا روشن شد")

    # ---------- ریست ----------
    @bot.cmd("ریست سلف", "reset", cat="عمومی", help="ریست سلف — پاک کردن همه تنظیمات این اکانت")
    async def _reset(event, ctx, args):
        from storage import default_account
        ctx.store.accs()[ctx.key] = default_account()
        ctx.store.save()
        await ctx.reply(event, "♻️ همه تنظیمات این اکانت پاک شد")
