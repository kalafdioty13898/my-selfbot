# -*- coding: utf-8 -*-
"""بمبر — ارسال تکراری یک پیام (نسخهٔ تک‌اکانته)

استفاده:
  روی پیام موردنظر (متن یا مدیا) ریپ بزن:  استارت بمبر 100
  اختیاری مقصد:  استارت بمبر 100 @username
  توقف:  توقف بمبر   |   وضعیت:  وضعیت بمبر
"""
import asyncio
import logging
import os
import random

from framework import Bot
from telethon.errors import FloodWaitError
from utils import tmp_path

log = logging.getLogger("selfbot")

MAX_COUNT = 1000      # سقف هر اجرا
DELAY = (0.6, 1.4)    # فاصلهٔ تصادفی بین ارسال‌ها (ضد فلود سخت تلگرام)
PROG_EVERY = 25       # هر چند پیام یک‌بار پیشرفت بدهد


def setup(bot: Bot):
    def _state(ctx):
        return ctx.extra.setdefault(
            "bomber", {"running": False, "stop": False, "sent": 0, "total": 0, "task": None})

    async def _bomb_job(ctx, target, text, media_path, total):
        st = _state(ctx)
        client = ctx.client
        prog = None
        try:
            while st["sent"] < total:
                if st["stop"]:
                    await ctx.send(target, f"🛑 بمبر متوقف شد — {st['sent']}/{total}")
                    return
                try:
                    if media_path:
                        await client.send_file(target, media_path, caption=text or None)
                    else:
                        await client.send_message(target, text)
                except FloodWaitError as e:
                    if e.seconds > 300:
                        await ctx.send(target, f"⏳ محدودیت تلگرام ({e.seconds}s) — بمبر خواست توقف؛ {st['sent']}/{total}")
                        return
                    await asyncio.sleep(e.seconds + 1)
                    continue
                except Exception as e:
                    await ctx.send(target, f"❌ خطا: {e.__class__.__name__} — توقف در {st['sent']}/{total}")
                    log.warning("bomber error: %s", e)
                    return
                st["sent"] += 1
                if st["sent"] % PROG_EVERY == 0 and st["sent"] < total:
                    try:
                        if prog is None:
                            prog = await client.send_message(target, f"📤 بمبر: {st['sent']}/{total}")
                        else:
                            await prog.edit(f"📤 بمبر: {st['sent']}/{total}")
                    except Exception:
                        prog = None
                await asyncio.sleep(random.uniform(*DELAY))
            await ctx.send(target, f"✅ بمبر تمام شد — {st['sent']}/{total}")
        finally:
            if media_path:
                try:
                    os.remove(media_path)
                except Exception:
                    pass
            st["running"] = False
            try:
                await ctx.send(ctx.relay_chat(), f"💣 بمبر: {st['sent']}/{total} به <code>{target}</code>",
                               parse_mode="html")
            except Exception:
                pass

    @bot.cmd("استارت بمبر", "startbomb", cat="ابزار",
             help="استارت بمبر <تعداد> — روی پیام موردنظر ریپ بزن؛ همان پیام N بار ارسال می‌شود. مقصد اختیاری: استارت بمبر 100 @user")
    async def _bomb_start(event, ctx, args):
        st = _state(ctx)
        if st["running"]:
            return await ctx.reply(event, "⚠️ بمبر در حال اجراست — اول «توقف بمبر»")
        parts = (args or "").split()
        if not parts:
            return await ctx.reply(event, "❗ فرمت: استارت بمبر 100")
        try:
            total = int(parts[0])
        except ValueError:
            return await ctx.reply(event, "❗ فرمت: استارت بمبر 100")
        if total < 1:
            return await ctx.reply(event, "❗ تعداد باید مثبت باشد")
        total = min(total, MAX_COUNT)

        rep = await event.get_reply_message()
        if not rep:
            return await ctx.reply(event, "❗ اول روی پیامی که باید فرستاده شود ریپ بزن")
        text = rep.raw_text or ""
        media_path = None
        if rep.media:
            try:
                media_path = await rep.download_media(file=tmp_path("bomb"))
            except Exception:
                media_path = None
        if not text and not media_path:
            return await ctx.reply(event, "❗ این پیام نه متن دارد نه مدیا")

        # مقصد: پیش‌فرض همین چت؛ با @username یا آیدی عددی هم می‌شود
        target = event.chat_id
        if len(parts) > 1:
            tok = parts[1]
            try:
                target = (int(tok) if tok.lstrip("-").isdigit()
                          else await ctx.client.get_entity(tok))
            except Exception:
                if media_path:
                    try:
                        os.remove(media_path)
                    except Exception:
                        pass
                return await ctx.reply(event, f"❗ مقصد «{tok}» پیدا نشد")

        st.update(running=True, stop=False, sent=0, total=total)
        where = getattr(target, "id", target)
        await ctx.reply(event, f"💣 بمبر شروع شد — {total} بار ارسال می‌شود (مقصد: <code>{where}</code>)\n"
                               f"🛑 توقف: «توقف بمبر»", parse_mode="html")
        st["task"] = asyncio.create_task(_bomb_job(ctx, target, text, media_path, total))

    @bot.cmd("توقف بمبر", "stopbomb", cat="ابزار",
             help="توقف بمبر — قطع بمبر در حال اجرا")
    async def _bomb_stop(event, ctx, args):
        st = _state(ctx)
        if not st["running"]:
            return await ctx.reply(event, "ℹ️ بمبری در حال اجرا نیست")
        st["stop"] = True
        await ctx.reply(event, f"🛑 دستور توقف ثبت شد — تا الان {st['sent']}/{st['total']}")

    @bot.cmd("وضعیت بمبر", "bombstatus", cat="ابزار",
             help="وضعیت بمبر — چند ارسال شده و چقدر مانده")
    async def _bomb_status(event, ctx, args):
        st = _state(ctx)
        if st["running"]:
            await ctx.reply(event, f"💣 بمبر فعال است — {st['sent']}/{st['total']}")
        else:
            await ctx.reply(event, "ℹ️ بمبری در حال اجرا نیست")
