# -*- coding: utf-8 -*-
"""ماژول مدیا: ذخیره محتوای restricted، دریافت استوری، ذخیره مدیای زمان‌دار (دستی و خودکار)."""
import html as _html
import os

from telethon.tl import functions, types

from framework import Bot
from utils import human_size, tmp_path, marked_id

MAX_DL = 512 * 1024 * 1024  # سقف دانلود ۵۱۲ مگ


def setup(bot: Bot):
    @bot.cmd("ذخیره", "save", cat="مدیا",
             help="ذخیره — روی پیام موردنظر ریپلی کن؛ فیلم/موزیک/عکس و پست‌های محدودشده ذخیره می‌شوند")
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

    # ---------- مدیای زمان‌دار (self-destruct) — حالت همگانی ----------
    @bot.cmd("ذخیره زماندار روشن", "ttlon", cat="مدیا",
             help="ذخیره زماندار روشن — در همه چت‌ها مدیای تایم‌دار خودکار ذخیره شود (حالت همگانی)")
    async def _ttlon(event, ctx, args):
        ctx.acc["ad"]["ttl"] = True
        ctx.store.save()
        await ctx.reply(event, "✅ ذخیره خودکار مدیای زمان‌دار در همه چت‌ها روشن شد")

    @bot.cmd("ذخیره زماندار خاموش", "ttloff", cat="مدیا",
             help="ذخیره زماندار خاموش — غیرفعال کردن حالت همگانی ذخیره تایم‌دار")
    async def _ttloff(event, ctx, args):
        ctx.acc["ad"]["ttl"] = False
        ctx.store.save()
        await ctx.reply(event, "✅ حالت همگانی ذخیره تایم‌دار خاموش شد")

    # ---------- ذخیره خودکار تایم‌دار — مخصوص هر چت (مثل چنل سلف) ----------
    @bot.cmd("ذخیره خودکار", "autosave", cat="مدیا",
             help="ذخیره خودکار [@کانال | خاموش | لیست] — داخل چتی که این دستور را می‌فرستی، هر عکس/فیلم/گیف/ویس تایم‌دار بدون ریپلی خودکار ذخیره می‌شود؛ مقصد: چت ذخیره‌سازی یا کانالی که می‌دهی")
    async def _autosave(event, ctx, args):
        a = (args or "").strip()
        key = str(event.chat_id)
        auto = ctx.acc.setdefault("autosave", {})
        if a in ("خاموش", "off", "غیرفعال"):
            if auto.pop(key, None) is None:
                return await ctx.reply(event, "ℹ️ ذخیره خودکار در این چت اصلاً روشن نبود")
            ctx.store.save()
            return await ctx.reply(event, "🔴 ذخیره خودکار این چت خاموش شد")
        if a in ("لیست", "list", "ها"):
            if not auto:
                return await ctx.reply(event, "ℹ️ هیچ چتی فعال نشده. داخل چت بفرست: ذخیره خودکار")
            rows = [f"• چت <code>{_html.escape(k)}</code> → مقصد <code>{_html.escape(str(v))}</code>"
                    for k, v in auto.items()]
            return await ctx.reply(event, "📍 ذخیره خودکار فعال:\n" + "\n".join(rows), parse_mode="html")
        if a:
            try:
                ent = await ctx.client.get_entity(
                    int(a) if a.lstrip("-").isdigit() else (a if a.startswith("@") else "@" + a))
                dest = marked_id(ent)
            except Exception:
                return await ctx.reply(
                    event, "❌ مقصد پیدا نشد! یوزرنیم کانال رو درست بده (مثل @self_me_me)")
        else:
            dest = "relay"  # چت ذخیره‌سازی پیش‌فرض: STORAGE_ID یا پیام‌های ذخیره‌شده
        auto[key] = dest
        ctx.store.save()
        d_txt = ("چت ذخیره‌سازی پیش‌فرض (STORAGE_ID یا پیام‌های ذخیره‌شده)"
                 if dest == "relay" else dest)
        await ctx.reply(
            event,
            "🟢 ذخیره خودکار تایم‌دار این چت روشن شد!\n"
            "📥 از این به بعد هر عکس/فیلم/گیف/ویس تایم‌دار که اینجا بیاد، "
            "بدون ریپلی خودکار ذخیره می‌شود.\n"
            f"📬 مقصد: {d_txt}\n"
            "⛔ خاموش کردن: «ذخیره خودکار خاموش»")

    # ---------- سیو چنل: فوروارد خودکار همه پست‌های یک کانال/چت ----------
    @bot.cmd("سیو چنل", "chsave", cat="مدیا",
             help="سیو چنل [@کانال | خاموش | لیست] — هر پست جدید این چت بدون ریپلی خودکار به پیام‌های ذخیره‌شده (یا مقصد دلخواه) فوروارد می‌شود")
    async def _chsave(event, ctx, args):
        a = (args or "").strip()
        key = str(event.chat_id)
        cs = ctx.acc.setdefault("chansave", {})
        if a in ("خاموش", "off", "غیرفعال"):
            if cs.pop(key, None) is None:
                return await ctx.reply(event, "ℹ️ سیو چنل برای این چت روشن نبود")
            ctx.store.save()
            return await ctx.reply(event, "🔴 سیو چنل این چت خاموش شد")
        if a in ("خاموش همه", "همه", "all"):
            n = len(cs)
            cs.clear()
            ctx.store.save()
            return await ctx.reply(event, f"🔴 سیو چنل همه چت‌ها خاموش شد ({n} مورد)")
        if a in ("لیست", "list", "ها"):
            if not cs:
                return await ctx.reply(event, "ℹ️ هیچ چتی فعال نشده. داخل کانال بفرست: سیو چنل")
            rows = [f"• چت <code>{_html.escape(k)}</code> → مقصد <code>{_html.escape(str(v))}</code>"
                    for k, v in cs.items()]
            return await ctx.reply(event, "📍 سیو چنل فعال:\n" + "\n".join(rows), parse_mode="html")
        if a:
            try:
                ent = await ctx.client.get_entity(
                    int(a) if a.lstrip("-").isdigit() else (a if a.startswith("@") else "@" + a))
                dest = marked_id(ent)
            except Exception:
                return await ctx.reply(
                    event, "❌ مقصد پیدا نشد! یوزرنیم کانال مقصد را بده (مثل @self_me_me)")
        else:
            dest = "relay"
        cs[key] = dest
        ctx.store.save()
        d_txt = ("چت ذخیره‌سازی پیش‌فرض (ست لاگ / STORAGE_ID / پیام‌های ذخیره‌شده)"
                 if dest == "relay" else dest)
        await ctx.reply(
            event,
            "🟢 سیو چنل روشن شد!\n"
            "📥 از این به بعد هر پست جدید این چت خودکار فوروارد می‌شود.\n"
            f"📬 مقصد: {d_txt}\n"
            "⛔ خاموش کردن: «سیو چنل خاموش»")

    @bot.msg_hook
    async def _chan_catch(event, ctx):
        msg = event.message
        if not msg or msg.out or msg.action:
            return
        cs = ctx.acc.get("chansave") or {}
        dest = cs.get(str(event.chat_id))
        if not dest:
            return
        dest_chat = ctx.relay_chat() if dest == "relay" else (
            int(dest) if str(dest).lstrip("-").isdigit() else dest)
        if str(dest_chat) == str(event.chat_id):
            return  # مقصد همان چت است — حلقه نشود
        try:
            await ctx.client.forward_messages(dest_chat, event.chat_id, msg.id)
        except Exception:
            # محتوای محافظت‌شده/فوروارد مسدود → کپی دستی
            try:
                if msg.media:
                    path = await msg.download_media(file=tmp_path("chan"))
                    if path:
                        await ctx.client.send_file(dest_chat, path)
                        os.remove(path)
                elif msg.raw_text:
                    await ctx.client.send_message(dest_chat, msg.raw_text)
            except Exception:
                pass

    @bot.msg_hook
    async def _ttl_catch(event, ctx):
        msg = event.message
        if not msg or msg.out:
            return
        media = msg.media
        ttl = getattr(media, "ttl_seconds", 0) if media else 0
        if not ttl or isinstance(media, (types.MessageMediaWebPage,)):
            return
        auto = ctx.acc.setdefault("autosave", {})
        dest = None
        d = auto.get(str(event.chat_id))
        if d is not None:
            if d == "relay":
                dest = ctx.relay_chat()
            elif str(d).lstrip("-").isdigit():
                dest = int(d)
            else:
                dest = d
            if str(dest) == str(event.chat_id):
                return  # مقصد همین چت است — حلقه نشود
        elif ctx.acc["ad"]["ttl"]:
            dest = ctx.relay_chat()
        if dest is None:
            return
        try:
            path = await msg.download_media(file=tmp_path("ttl"))
            if path:
                await ctx.client.send_file(
                    dest, path,
                    caption="⏲ مدیای زمان‌دار (قبل از حذف شدن ذخیره شد)")
                os.remove(path)
        except Exception:
            pass
