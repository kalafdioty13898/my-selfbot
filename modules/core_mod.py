# -*- coding: utf-8 -*-
"""ماژول هسته: پنل عکسی با دکمه‌های شیشه‌ای، پینگ، وضعیت، روشن/خاموش کردن سلف."""
import html as _html

from telethon import Button

from framework import Bot
from utils import chunk_text, now, to_jalali, tmp_path

# ترتیب دکمه‌های پنل + آیکون هر بخش (فقط بخش‌های موجود نشان داده می‌شوند)
CATS = [
    ("پروفایل", "👤"), ("گروه", "👥"), ("منشی", "🤖"), ("یادآور", "⏰"),
    ("مدیا", "💾"), ("آنتی‌حذف", "🛡️"), ("ترجمه", "🌐"), ("پاسخ سریع", "💬"),
    ("ابری", "☁️"), ("عمومی", "🧩"),
]

CAPTION_MAX = 1000  # سقف کپشن تلگرام 1024 است
SEP = "──────────────────"


def setup(bot: Bot):
    # ---------- پنل عکسی با دکمه شیشه‌ای ----------
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

    def _compact(cat, lines):
        out = f"📌 <b>{cat}</b>\n\n"
        for h in lines:
            cmd_part, _, desc = h.partition(" — ")
            row = f"• <code>{_html.escape(cmd_part.strip())}</code>"
            if desc:
                row += " — " + _html.escape(desc if len(desc) <= 60 else desc[:57] + "…")
            out += row + "\n"
        return out

    def _home_caption(ctx):
        n = now(ctx.cfg.tz)
        jy, jm, jd = to_jalali(n.date())
        uname = ("@" + ctx.me.username) if getattr(ctx.me, "username", None) else "—"
        return ("🤖 <b>پنل سلف‌بوت شخصی</b>\n"
                f"👤 {_html.escape(ctx.me.first_name or '')}\n"
                f"🆔 <code>{ctx.me_id}</code>  |  {uname}\n"
                f"🕐 {n.strftime('%H:%M')}  |  📅 {jy}/{jm:02d}/{jd:02d}\n"
                f"<i>👇 یکی از دکمه‌های شیشه‌ای را بزن</i>")

    def _home_buttons(avail, with_back=False):
        rows, row = [], []
        for i, (cat, icon) in enumerate(avail):
            row.append(Button.inline(f"{icon} {cat}", f"p:{i}".encode()))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([Button.inline("📊 وضعیت", b"p:s")])
        if with_back:
            rows.append([Button.inline("🔄 بازگشت", b"p:h")])
        return rows

    async def _send_panel(event, ctx):
        cap = _home_caption(ctx)
        btns = _home_buttons(_avail())
        path = None
        try:
            path = await ctx.client.download_profile_media(ctx.me, file=tmp_path("jpg"))
        except Exception:
            path = None
        if path:
            try:
                await ctx.client.send_file(event.chat_id, path, caption=cap,
                                           parse_mode="html", buttons=btns)
                return
            except Exception:
                pass
        await ctx.reply(event, cap, parse_mode="html", buttons=btns)

    @bot.cmd("راهنما", "help", "پنل", always=True, cat="عمومی",
             help="راهنما [بخش] — پنل عکسی با دکمه‌های شیشه‌ای؛ متن کامل یک بخش: راهنما مدیا")
    async def _help(event, ctx, args):
        if not args.strip():
            return await _send_panel(event, ctx)
        head = "🤖 <b>پنل سلف‌بوت شخصی</b>\n" + f"{'═' * 30}\n"
        want = args.strip()
        for cat, lines in _sections().items():
            if want in (cat, cat.strip("#")) or want.lower() in (c.lower() for c in _en_cat(cat)):
                body = f"\n📘 <b>راهنمای {cat}</b>\n" + "\n\n".join(_block(h) for h in lines)
                for part in chunk_text(head + body):
                    await ctx.reply(event, part, parse_mode="html")
                return
        await ctx.reply(event, "❌ چنین بخشی پیدا نشد. فقط «راهنما» بفرست تا کل پنل بیاد.")

    def _en_cat(cat):
        m = {"عمومی": ["عمومی", "core"], "مدیا": ["مدیا", "media"],
             "آنتی‌حذف": ["antidelete"], "منشی": ["secretary"],
             "پاسخ سریع": ["quick"], "پروفایل": ["profile"],
             "گروه": ["group"], "یادآور": ["reminder"],
             "ترجمه": ["translate"], "ابری": ["cloud"]}
        return m.get(cat, [cat])

    @bot.cb_hook
    async def _panel_cb(event, ctx):
        data = (event.data or b"").decode("utf-8", "ignore")
        if not data.startswith("p:"):
            await event.answer()
            return
        if not ctx.is_sudo(event.sender_id or 0):
            return await event.answer("⛔ این پنل مال تو نیست!", alert=True)
        key = data[2:]
        avail = _avail()
        if key == "h":
            await event.edit(_home_caption(ctx), parse_mode="html",
                             buttons=_home_buttons(avail))
        elif key == "s":
            await event.edit(_status_text(ctx), parse_mode="html",
                             buttons=_home_buttons(avail, with_back=True))
        elif key.isdigit() and int(key) < len(avail):
            cat, _icon = avail[int(key)]
            cap = _compact(cat, _sections().get(cat, []))
            if len(cap) > CAPTION_MAX:
                cap = cap[:CAPTION_MAX] + "\n…\n💡 متن کامل: راهنما " + cat
            await event.edit(cap, parse_mode="html",
                             buttons=_home_buttons(avail, with_back=True))
        await event.answer()

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
