# -*- coding: utf-8 -*-
"""ماژول هسته: پنل عکسی با منوی شماره‌ای، پینگ، وضعیت، روشن/خاموش کردن سلف.

نکته: تلگرام اجازه دکمه اینلاین فقط به بات‌ها می‌دهد؛ اکانت یوزر نمی‌تواند،
پس منو شماره‌ای است: «پنل 2» یا «پنل منشی»."""
import html as _html

from framework import Bot
from utils import chunk_text, now, to_jalali, tmp_path

# ترتیب بخش‌های پنل + آیکون هر بخش (فقط بخش‌های موجود نشان داده می‌شوند)
CATS = [
    ("پروفایل", "👤"), ("گروه", "👥"), ("منشی", "🤖"), ("یادآور", "⏰"),
    ("مدیا", "💾"), ("آنتی‌حذف", "🛡️"), ("ترجمه", "🌐"), ("پاسخ سریع", "💬"),
    ("ابری", "☁️"), ("عمومی", "🧩"),
]

SEP = "──────────────────"
NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def setup(bot: Bot):
    # ---------- پنل عکسی با منوی شماره‌ای ----------
    def _sections():
        out = {}
        for _aliases, _fn, _always, cat, hlp in bot.cmds:
            if hlp:
                out.setdefault(cat, []).append(hlp)
        return out

    def _avail():
        have = set(_sections().keys())
        return [(cat, icon) for cat, icon in CATS if cat in have]

    def _block(hlp):
        # فرمت «دستور — توضیح» → توضیح، جداکننده، دستور قابل کپی با ضربه
        if " — " in hlp:
            cmd_part, desc = hlp.split(" — ", 1)
        else:
            cmd_part, desc = hlp, ""
        out = ""
        if desc:
            out += _html.escape(desc) + "\n"
        out += SEP + "\n"
        out += "دستور ---> <code>" + _html.escape(cmd_part.strip()) + "</code>"
        return out

    def _menu_text(ctx):
        n = now(ctx.cfg.tz)
        jy, jm, jd = to_jalali(n.date())
        uname = ("@" + ctx.me.username) if getattr(ctx.me, "username", None) else "—"
        avail = _avail()
        menu = "\n".join(
            f"{NUMS[i]} {icon} <b>{cat}</b>  →  <code>پنل {i + 1}</code>"
            for i, (cat, icon) in enumerate(avail))
        return ("🤖 <b>پنل سلف‌بوت شخصی</b>\n"
                f"👤 {_html.escape(ctx.me.first_name or '')}\n"
                f"🆔 <code>{ctx.me_id}</code>  |  {uname}\n"
                f"🕐 {n.strftime('%H:%M')}  |  📅 {jy}/{jm:02d}/{jd:02d}\n"
                + SEP + "\n"
                "<i>بخش را باز کن — شماره یا اسمش را بفرست:</i>\n"
                + menu
                + "\n" + SEP + "\n"
                "📊 وضعیت  →  <code>پنل وضعیت</code>\n"
                "🔄 منوی اول  →  <code>پنل</code>")

    async def _send_panel(event, ctx):
        cap = _menu_text(ctx)
        path = None
        try:
            path = await ctx.client.download_profile_media(ctx.me, file=tmp_path("jpg"))
        except Exception:
            path = None
        if path:
            try:
                await ctx.client.send_file(event.chat_id, path, caption=cap,
                                           parse_mode="html")
                return
            except Exception:
                pass
        await ctx.reply(event, cap, parse_mode="html")

    def _find_section(want):
        """شماره یا اسم بخش را پیدا کند؛ None یعنی پیدا نشد."""
        avail = _avail()
        if want.isdigit() and 1 <= int(want) <= len(avail):
            return avail[int(want) - 1][0]
        for cat, _icon in avail:
            if want in (cat, cat.strip("#")) or want.lower() in (c.lower() for c in _en_cat(cat)):
                return cat
        return None

    @bot.cmd("راهنما", "help", "پنل", always=True, cat="عمومی",
             help="پنل — پنل عکسی با منوی بخش‌ها (پنل 2 یا پنل منشی)؛ راهنما مدیا — توضیح کامل یک بخش")
    async def _help(event, ctx, args):
        if not args.strip():
            return await _send_panel(event, ctx)
        want = args.strip()
        if want in ("وضعیت", "status"):
            return await ctx.reply(event, _status_text(ctx), parse_mode="html")
        cat = _find_section(want)
        if cat is None:
            return await ctx.reply(event,
                                   "❌ چنین بخشی پیدا نشد. فقط «پنل» بفرست تا منوی کامل بیاد.")
        head = "🤖 <b>پنل سلف‌بوت شخصی</b>\n" + f"{'═' * 30}\n"
        body = f"\n📘 <b>راهنمای {cat}</b>\n" + "\n\n".join(_block(h) for h in _sections()[cat])
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
    def _status_text(ctx):
        acc = ctx.acc
        up = int(now(ctx.cfg.tz).timestamp() - ctx.started)
        clk = acc.get("clk", {})
        return (f"📊 <b>وضعیت سلف</b>\n"
                f"👤 اکانت: {(ctx.me.first_name or '')} (<code>{ctx.me_id}</code>)\n"
                f"⏱ فعال بودن: {up // 3600} ساعت و {up % 3600 // 60} دقیقه\n"
                f"🔌 وضعیت: {'🔴 خاموش (همگانی)' if acc['off']['all'] else '🟢 روشن'}\n"
                f"⚡ پاسخ سریع: {len(acc['quick'])} عدد\n"
                f"☁️ ذخیره ابری: {len(acc['cloud'])} عدد\n"
                f"⏰ یادآور فعال: {len(acc['rems'])} | هشدار روزانه: {len(acc['daily'])}\n"
                f"👤 اسم‌های چرخشی: {len(acc['names'])} ({'روشن' if acc['names_on'] else 'خاموش'})"
                f" | ⌚ ساعت اسم: {'روشن' if clk.get('name_on') else 'خاموش'}\n"
                f"📝 بیوهای چرخشی: {len(acc['bios'])} ({'روشن' if acc['bios_on'] else 'خاموش'})"
                f" | ⌚ ساعت بیو: {'روشن' if clk.get('bio_on') else 'خاموش'}\n"
                f"🤖 منشی: {'✅' if acc['sec']['on'] else '❌'} (حالت {acc['sec']['mode']})\n"
                f"🛡 آنتی‌حذف: {'✅' if acc['ad']['del'] else '❌'}")

    @bot.cmd("وضعیت", "status", always=True, cat="عمومی", help="وضعیت — گزارش کامل سلف")
    async def _status(event, ctx, args):
        await ctx.reply(event, _status_text(ctx), parse_mode="html")

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
