# -*- coding: utf-8 -*-
"""ارسال زمان‌دار — پیام (متن یا ریپ مدیا) سر ساعت مشخص خودش ارسال می‌شود

استفاده:
  زمان‌دار 21:30 خوب شب بخیر
  (ریپ روی یک پیام/مدیا)  زمان‌دار 21:30     ← همان پیام کپی می‌شود
  زمان‌دارها                      ← لیست
  حذف زمان‌دار 2                  ← حذف از لیست
ساعت بعدیِ همان روز؛ اگر گذشته باشد فردا. تاریخ شمسی شهر هم پشتیبانی می‌شود.
"""
import asyncio
import time

from framework import Bot
from utils import render_vars

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _parse_hhmm(s):
    """«21:30» یا «۲۱:۳۰» → (21, 30) یا None."""
    s = (s or "").strip().translate(_PERSIAN_DIGITS)
    if ":" not in s:
        return None
    h, _, m = s.partition(":")
    if not (h.isdigit() and m.isdigit()):
        return None
    h, m = int(h), int(m)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h, m


def _next_epoch(h, m, now=None):
    """بعدین زمانِ امروز با ساعت h:m؛ اگر گذشته فردا."""
    now = now or time.time()
    lt = time.localtime(now)
    tgt = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))
    if tgt <= now:
        tgt += 86400
    return tgt


def _fmt_at(epoch):
    return time.strftime("%H:%M", time.localtime(epoch))


def setup(bot: Bot):
    @bot.cmd("زمان‌دار", "later", cat="یادآور",
             help="زمان‌دار HH:MM <متن> — ارسال سرِ ساعت در همین چت؛ "
                  "یا ریپ روی پیام/مدیا: زمان‌دار HH:MM")
    async def _later(event, ctx, args):
        parts = (args or "").strip().split(None, 1)
        hm = _parse_hhmm(parts[0]) if parts else None
        if not hm:
            return await ctx.reply(event, "❗ فرمت: زمان‌دار 21:30 خوب شب بخیر")
        text, src_chat, src_msg = "", None, None
        if len(parts) > 1 and parts[1].strip():
            text = parts[1].strip()
        else:
            rep = None
            try:
                rep = await event.get_reply_message()
            except Exception:
                rep = None
            if not rep:
                return await ctx.reply(event, "❗ متن بده یا روی پیامی ریپ بزن")
            text = rep.raw_text or ""
            src_chat, src_msg = event.chat_id, rep.id
            if not text and not rep.media:
                return await ctx.reply(event, "❗ این پیام نه متن دارد نه مدیا")
        at = _next_epoch(*hm)
        ctx.acc["later"].append({"at": at, "chat": event.chat_id,
                                 "text": text, "src_chat": src_chat, "src_msg": src_msg})
        ctx.store.save()
        await ctx.reply(event, f"⏰ شد — {_fmt_at(at)} ارسال می‌شود\n💬 {text[:60] or '(مدیا از ریپلی)'}")

    @bot.cmd("زمان‌دارها", "laters", cat="یادآور",
             help="زمان‌دارها — لیست ارسال‌های زمان‌دار")
    async def _laters(event, ctx, args):
        items = ctx.acc["later"]
        if not items:
            return await ctx.reply(event, "ℹ️ چیزی زمان‌دار نکردی")
        items.sort(key=lambda x: x.get("at", 0))
        lines = ["⏰ ارسال‌های زمان‌دار:"]
        for i, r in enumerate(items, 1):
            prev = (r.get("text") or "(مدیا)")[:40]
            lines.append(f"{i}. 🕒 {_fmt_at(r['at'])} — {prev}")
        await ctx.reply(event, "\n".join(lines))

    @bot.cmd("حذف زمان‌دار", "laterdel", cat="یادآور",
             help="حذف زمان‌دار <شماره> — شماره از «زمان‌دارها»")
    async def _later_del(event, ctx, args):
        items = sorted(ctx.acc["later"], key=lambda x: x.get("at", 0))
        try:
            i = int((args or "").strip().translate(_PERSIAN_DIGITS)) - 1
        except ValueError:
            return await ctx.reply(event, "❗ فرمت: حذف زمان‌دار 2")
        if not (0 <= i < len(items)):
            return await ctx.reply(event, "❗ شماره درست نیست — «زمان‌دارها» را ببین")
        ctx.acc["later"].remove(items[i])
        ctx.store.save()
        await ctx.reply(event, f"🗑 حذف شد: {_fmt_at(items[i]['at'])} — {(items[i].get('text') or '(مدیا)')[:40]}")

    @bot.tick_hook
    async def _tick(ctx):
        items = ctx.acc["later"]
        if not items:
            return
        now = time.time()
        due = [r for r in items if r.get("at", 0) <= now]
        if not due:
            return
        client = ctx.client
        for r in due:
            items.remove(r)
            try:
                text = render_vars(r.get("text") or "")
                if r.get("src_msg"):
                    try:
                        src = await client.get_messages(r["src_chat"], ids=r["src_msg"])
                    except Exception:
                        src = None
                    if isinstance(src, list):  # احتیاط: بعضی نسخه‌ها لیست می‌دهند
                        src = src[0] if src else None
                    if src is not None:
                        await client.send_message(r["chat"], text or None,
                                                  file=src.media if src.media else None)
                    else:
                        await ctx.send(r["chat"], text or "(پیام زمان‌دار — منبع پیدا نشد)")
                else:
                    await ctx.send(r["chat"], text)
            except Exception:
                try:
                    items.remove(r)
                except Exception:
                    pass
                try:
                    await ctx.send(ctx.relay_chat(), f"⚠️ ارسال زمان‌دار شکست: {r.get('text', '')[:50]}")
                except Exception:
                    pass
            await asyncio.sleep(0.5)
        ctx.store.save()
