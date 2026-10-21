# -*- coding: utf-8 -*-
"""ماژول مدیا: ذخیره محتوای restricted، دریافت استوری، ذخیره مدیای زمان‌دار."""
import os

from telethon.tl import functions, types

from framework import Bot
from utils import human_size, tmp_path

MAX_DL = 512 * 1024 * 1024  # سقف دانلود ۵۱۲ مگ


def setup(bot: Bot):
    @bot.cmd("ذخیره", "save", cat="مدیا",
             help="ذخیره / !save (ریپلی) — ذخیره پست محدودشده (فیلم/موزیک/عکس)")
    async def _save(event, ctx, args):
        if not event.is_reply:
            return await ctx.reply(event, "❗ روی پیام موردنظر ریپلی کن")
        src = await event.get_reply_message()
        if not src or not src.media:
            if src and src.raw_text:
                await ctx.client.send_message(ctx.relay_chat(), src.raw_text)
                return await ctx.reply(event, "✅ متن ذخیره شد")
            return await ctx.reply(event, "❗ این پیام مدیا نداره")
        note = await ctx.reply(event, "⏳ در حال دانلود...")
        try:
            if src.file and src.file.size and src.file.size > MAX_DL:
                return await ctx.client.edit_message(event.chat_id, note.id,
                                                     f"❌ فایل بزرگ‌تر از {human_size(MAX_DL)} است")
            path = await src.download_media(file=tmp_path(src.file.ext.lstrip(".") if src.file and src.file.ext else "bin"))
            caption = f"💾 ذخیره‌شده از {getattr(event.chat, 'title', None) or 'چت'}"
            await ctx.client.send_file(ctx.relay_chat(), path, caption=caption)
            os.remove(path)
            await ctx.client.edit_message(event.chat_id, note.id, "✅ ذخیره شد")
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ خطا: {e}")

    @bot.cmd("دریافت استوری", "stories", cat="مدیا",
             help="دریافت استوری @user — گرفتن استوری‌های یک کاربر")
    async def _stories(event, ctx, args):
        target = (args or "").strip().lstrip("@")
        if not target and event.is_reply:
            m = await event.get_reply_message()
            target = m.sender_id
        if not target:
            return await ctx.reply(event, "❗ یوزرنیم بده: دریافت استوری @user")
        try:
            entity = await ctx.client.get_entity(target)
        except Exception:
            return await ctx.reply(event, "❌ کاربر پیدا نشد")
        note = await ctx.reply(event, "🔎 در حال بررسی استوری‌ها...")
        try:
            res = await ctx.client(functions.stories.GetPeerStoriesRequest(
                peer=await ctx.client.get_input_entity(entity)))
            items = list(getattr(res, "stories", []) or [])
            items = [s for s in items if getattr(s, "media", None)]
            if not items:
                return await ctx.client.edit_message(event.chat_id, note.id, "ℹ️ استوری فعالی نداره")
            await ctx.client.edit_message(event.chat_id, note.id,
                                          f"⏳ {len(items)} استوری پیدا شد، دارم میارم...")
            for s in items[:20]:
                try:
                    path = await ctx.client.download_media(s.media, file=tmp_path("story"))
                    await ctx.client.send_file(event.chat_id, path,
                                               caption=f"📷 استوری {getattr(entity, 'first_name', '') or getattr(entity, 'title', '')}")
                    os.remove(path)
                except Exception:
                    continue
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ خطا: {e}")

    # ---------- مدیای زمان‌دار (self-destruct) ----------
    @bot.cmd("ذخیره زماندار روشن", "ttlon", cat="مدیا",
             help="ذخیره زماندار روشن — عکس/فیلم زمان‌دار خودکار ذخیره شود")
    async def _ttlon(event, ctx, args):
        ctx.acc["ad"]["ttl"] = True
        ctx.store.save()
        await ctx.reply(event, "✅ ذخیره خودکار مدیای زمان‌دار روشن شد")

    @bot.cmd("ذخیره زماندار خاموش", "ttloff", cat="مدیا",
             help="ذخیره زماندار خاموش — غیرفعال کردن ذخیره زمان‌دار")
    async def _ttloff(event, ctx, args):
        ctx.acc["ad"]["ttl"] = False
        ctx.store.save()
        await ctx.reply(event, "✅ ذخیره خودکار مدیای زمان‌دار خاموش شد")

    @bot.msg_hook
    async def _ttl_catch(event, ctx):
        msg = event.message
        if not msg or not ctx.acc["ad"]["ttl"]:
            return
        media = msg.media
        ttl = getattr(media, "ttl_seconds", 0) if media else 0
        if not ttl or isinstance(media, (types.MessageMediaWebPage,)):
            return
        try:
            path = await msg.download_media(file=tmp_path("ttl"))
            if path:
                await ctx.client.send_file(
                    ctx.relay_chat(), path,
                    caption="⏲ مدیای زمان‌دار (قبل از حذف شدن ذخیره شد)")
                os.remove(path)
        except Exception:
            pass
