# -*- coding: utf-8 -*-
"""ماژول یادآور: یادآور دقیقه‌ای، هشدار روزانه، حذف خودکار پیام."""
import asyncio
import time

from framework import Bot
from utils import now


def setup(bot: Bot):
    # ---------- یادآور ----------
    @bot.cmd("یادآور", "remind", cat="یادآور",
             help="یادآور <دقیقه> <متن> — بعد از مدتی یادت بیندازد، مثال: یادآور 30 برو دارو بخور")
    async def _remind(event, ctx, args):
        parts = (args or "").strip().split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit():
            return await ctx.reply(event, "❗ فرمت: یادآور 30 متن پیام")
        mins = int(parts[0])
        if mins < 1 or mins > 60 * 24 * 30:
            return await ctx.reply(event, "❗ بین ۱ دقیقه تا ۳۰ روز")
        ctx.acc["rems"].append({"ts": time.time() + mins * 60,
                                "chat": event.chat_id, "text": parts[1].strip()})
        ctx.store.save()
        await ctx.reply(event, f"⏰ باشه، {mins} دقیقه دیگه یادت میندازم")

    @bot.cmd("یادآور ها", "rems", cat="یادآور",
             help="یادآور ها — لیست یادآورهای فعال")
    async def _rems(event, ctx, args):
        rems = ctx.acc["rems"]
        if not rems:
            return await ctx.reply(event, "ℹ️ یادآوری ثبت نشده")
        n = now(ctx.cfg.tz)
        lines = []
        for i, r in enumerate(rems):
            left = int(r["ts"] - n.timestamp())
            lines.append(f"{i + 1}. [{r['chat']}] {max(0, left) // 60} دقیقه دیگه — {r['text'][:40]}")
        await ctx.reply(event, "⏰ یادآورها:\n" + "\n".join(lines))

    @bot.cmd("حذف یادآور", "remdel", cat="یادآور",
             help="حذف یادآور <شماره> — حذف از لیست یادآور")
    async def _rem_del(event, ctx, args):
        try:
            i = int(args.strip()) - 1
            ctx.acc["rems"].pop(i)
            ctx.store.save()
            await ctx.reply(event, "✅ حذف شد")
        except Exception:
            await ctx.reply(event, "❗ شماره معتبر بده (لیست: یادآور ها)")

    # ---------- هشدار روزانه ----------
    @bot.cmd("هشدار جدید", "alertadd", cat="یادآور",
             help="هشدار جدید <HH:MM> <متن> — هر روز در این ساعت در همین چت ارسال شود")
    async def _alert_add(event, ctx, args):
        parts = (args or "").strip().split(None, 1)
        if len(parts) < 2 or ":" not in parts[0]:
            return await ctx.reply(event, "❗ فرمت: هشدار جدید 21:30 مثلا «برو ورزش کن»")
        try:
            hh, mm = map(int, parts[0].split(":"))
            assert 0 <= hh < 24 and 0 <= mm < 60
        except Exception:
            return await ctx.reply(event, "❗ ساعت معتبر بده مثل 21:30")
        ctx.acc["daily"].append({"chat": event.chat_id, "hh": hh, "mm": mm,
                                 "text": parts[1].strip(), "last": ""})
        ctx.store.save()
        await ctx.reply(event, f"✅ هشدار روزانه {hh:02d}:{mm:02d} ثبت شد")

    @bot.cmd("هشدار ها", "alerts", cat="یادآور",
             help="هشدار ها — لیست هشدارهای روزانه")
    async def _alerts(event, ctx, args):
        d = ctx.acc["daily"]
        if not d:
            return await ctx.reply(event, "ℹ️ هشداری ثبت نشده")
        lines = [f"{i + 1}. [{a['chat']}] {a['hh']:02d}:{a['mm']:02d} — {a['text'][:40]}"
                 for i, a in enumerate(d)]
        await ctx.reply(event, "⏰ هشدارهای روزانه:\n" + "\n".join(lines))

    @bot.cmd("حذف هشدار", "alertdel", cat="یادآور",
             help="حذف هشدار <شماره> — حذف هشدار روزانه")
    async def _alert_del(event, ctx, args):
        try:
            i = int(args.strip()) - 1
            ctx.acc["daily"].pop(i)
            ctx.store.save()
            await ctx.reply(event, "✅ حذف شد")
        except Exception:
            await ctx.reply(event, "❗ شماره معتبر بده (لیست: هشدار ها)")

    # ---------- حذف خودکار ----------
    @bot.cmd("حذف خودکار", "autodel", cat="یادآور",
             help="حذف خودکار <دقیقه> (ریپلی) — این پیام بعد از مدتی پاک شود")
    async def _autodel(event, ctx, args):
        try:
            mins = int(args.strip())
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: حذف خودکار 5")
        if not event.is_reply:
            return await ctx.reply(event, "❗ روی پیام ریپلی کن")
        m = await event.get_reply_message()

        async def _later():
            await asyncio.sleep(mins * 60)
            try:
                await ctx.client.delete_messages(event.chat_id, [m.id, note.id])
            except Exception:
                pass
        note = await ctx.reply(event, f"⏲ این پیام تا {mins} دقیقه دیگه پاک میشه")
        asyncio.create_task(_later())

    @bot.cmd("حذف روشن", "autodelon", cat="یادآور",
             help="حذف روشن <دقیقه> — همه پیام‌های خودت در این چت بعد از X دقیقه پاک شوند")
    async def _autodel_on(event, ctx, args):
        try:
            mins = max(1, int(args.strip()))
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: حذف روشن 5")
        ctx.acc["autodel"][_chat_key(event.chat_id)] = mins
        ctx.store.save()
        await ctx.reply(event, f"✅ پیام‌هایت در این چت بعد از {mins} دقیقه پاک می‌شوند")

    @bot.cmd("حذف خاموش", "autodeloff", cat="یادآور",
             help="حذف خاموش — پایان حذف خودکار این چت")
    async def _autodel_off(event, ctx, args):
        ctx.acc["autodel"].pop(str(event.chat_id), None)
        ctx.store.save()
        await ctx.reply(event, "✅ حذف خودکار این چت خاموش شد")

    bot._chat_key = str  # noqa — برای استفاده داخلی

    @bot.out_hook
    async def _autodel_out(event, ctx):
        mins = ctx.acc["autodel"].get(str(event.chat_id))
        if not mins:
            return
        msg = event.message

        async def _later():
            await asyncio.sleep(mins * 60)
            try:
                await ctx.client.delete_messages(event.chat_id, [msg.id])
            except Exception:
                pass
        asyncio.create_task(_later())

    # ---------- تیک‌ها ----------
    @bot.tick_hook
    async def _tick(ctx):
        n = now(ctx.cfg.tz)
        ts = n.timestamp()
        # یادآورها
        due = [r for r in ctx.acc["rems"] if r["ts"] <= ts]
        if due:
            ctx.acc["rems"] = [r for r in ctx.acc["rems"] if r["ts"] > ts]
            ctx.store.save()
            for r in due:
                await ctx.send(r["chat"], f"⏰ یادآور: {r['text']}")
        # هشدارهای روزانه
        cur = f"{n.month}-{n.day}"
        changed = False
        for a in ctx.acc["daily"]:
            key = f"{n.year}-{cur}"
            if a["hh"] == n.hour and a["mm"] == n.minute and a.get("last") != key:
                a["last"] = key
                changed = True
                await ctx.send(a["chat"], f"🔔 {a['text']}")
        if changed:
            ctx.store.save()
