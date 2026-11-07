# -*- coding: utf-8 -*-
"""ماژول مدیا: ذخیره محتوای restricted، دریافت استوری، ذخیره مدیای زمان‌دار (دستی و خودکار)،
سیو از لینک t.me (چنل‌های فوروارد‌بسته) + سیو خودکار لینک در سیو مسیج."""
import html as _html
import os
import re as _re

from telethon.tl import functions, types

from framework import Bot
from utils import human_size, tmp_path, marked_id, media_ext

MAX_DL = 512 * 1024 * 1024  # سقف دانلود ۵۱۲ مگ

# ---------- لینک t.me → پست ----------
_TME_RE = _re.compile(r"(?:https?://)?(?:t|telegram)\.me/\S+", _re.I)
_TME_C_RE = _re.compile(
    r"(?:https?://)?(?:t|telegram)\.me/c/(\d+)(?:/(\d+))?(?:/(\d+))?", _re.I)
_TME_PUB_RE = _re.compile(
    r"(?:https?://)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,31})"
    r"(?:/(\d+))?(?:/(\d+))?", _re.I)
_RESERVED = {"c", "s", "joinchat", "share", "addstickers", "addemoji",
             "addtheme", "addlist", "proxy", "socks", "importfolder",
             "start", "contact", "setlanguage", "contactimport"}


def parse_tme_link(link):
    """لینک t.me → (ref, msg_id, single)؛ ref = '@user' یا int آیدی داخلی.
    پشتیبانی: t.me/chan/123 | t.me/c/1234567/89 | t.me/c/1234567/5/89 (تاپیک)
    | ?single برای تک‌پیامِ آلبوم. None = لینک پست نیست."""
    link = (link or "").strip()
    q = "single" in link.lower().split("?", 1)[-1] if "?" in link else False
    link = link.split("?", 1)[0].rstrip("/")
    m = _TME_C_RE.match(link)
    if m:
        cid, a, b = m.group(1), m.group(2), m.group(3)
        mid = int(b) if b else (int(a) if a else 0)
        return (int(cid), mid, q) if mid else None
    m = _TME_PUB_RE.match(link)
    if m:
        un = m.group(1)
        if un.lower() in _RESERVED:
            return None
        a, b = m.group(2), m.group(3)
        mid = int(b) if b else (int(a) if a else 0)
        return ("@" + un, mid, q) if mid else None
    return None


async def _do_save_link(event, ctx, link_text, reply_to, note=None):
    """پستِ لینک t.me را از چشمه می‌گیرد، با پسوند واقعی دانلود و در همین چت می‌فرستد.
    چنل‌های فوروارد‌بسته: دانلود مستقیم از چشمه کار می‌کند، فقط فوروارد بسته است.
    خروجی True/False؛ note = پیام «⏳...» که همان جا ویرایش می‌شود."""
    parsed = parse_tme_link(link_text)
    if not parsed:
        return False
    ref, mid, single = parsed
    try:
        if isinstance(ref, int):
            from telethon.tl.types import PeerChannel
            ent = await ctx.client.get_entity(PeerChannel(ref))
        else:
            ent = await ctx.client.get_entity(ref)
    except Exception:
        msg = ("❌ به این چت دسترسی ندارم — برای لینک خصوصی (t.me/c/...) "
               "اکانت باید عضو آن چت باشد")
        if note:
            await ctx.client.edit_message(event.chat_id, note.id, msg)
        else:
            await ctx.reply(event, msg)
        return False
    label = (("@" + ent.username) if getattr(ent, "username", None)
             else (getattr(ent, "title", None) or "چت"))
    try:
        if single:
            msgs = [await ctx.client.get_messages(ent, ids=mid)]
        else:
            batch = await ctx.client.get_messages(ent, ids=list(range(mid, mid + 10)))
            base = batch[0] if batch else None
            gid = getattr(base, "grouped_id", None) if base else None
            if gid:
                msgs = [m for m in batch if m and getattr(m, "grouped_id", None) == gid]
            else:
                msgs = [base] if base else []
        msgs = [m for m in msgs if m]
        if not msgs:
            msg = "ℹ️ این پست پیدا نشد (حذف شده یا لینک ناقص است)"
            if note:
                await ctx.client.edit_message(event.chat_id, note.id, msg)
            else:
                await ctx.reply(event, msg)
            return False
        media_msgs = [m for m in msgs if m.media]
        if not media_msgs:
            txt = "\n".join((m.raw_text or "") for m in msgs).strip()
            if not txt:
                if note:
                    await ctx.client.edit_message(event.chat_id, note.id,
                                                  "ℹ️ این پست نه مدیا دارد نه متن")
                return False
            await ctx.client.send_message(event.chat_id, txt, reply_to=reply_to)
            if note:
                await ctx.client.edit_message(event.chat_id, note.id, "✅ متن پست ذخیره شد")
            return True
        for m in media_msgs:
            if m.file and m.file.size and m.file.size > MAX_DL:
                msg = f"❌ فایل بزرگ‌تر از {human_size(MAX_DL)} است"
                if note:
                    await ctx.client.edit_message(event.chat_id, note.id, msg)
                else:
                    await ctx.reply(event, msg)
                return False
        paths, caps = [], []
        for m in media_msgs:
            p = await m.download_media(file=tmp_path(media_ext(m)))
            if p:
                paths.append(p)
                caps.append((m.raw_text or "").strip())
        if not paths:
            if note:
                await ctx.client.edit_message(event.chat_id, note.id, "❌ دانلود نشد")
            return False
        if len(paths) > 1:
            caption = caps if any(caps) else f"💾 سیو از {label}"
        else:
            caption = caps[0] or f"💾 سیو از {label}"
        sent = await ctx.client.send_file(
            event.chat_id, paths if len(paths) > 1 else paths[0],
            caption=caption, reply_to=reply_to)
        try:
            ctx.extra.setdefault("ls_skip", set()).add(getattr(sent, "id", None))
        except Exception:
            pass
        if note:
            await ctx.client.edit_message(
                event.chat_id, note.id,
                f"✅ سیو شد از {label}"
                + (f" ({len(paths)} فایل آلبوم)" if len(paths) > 1 else ""))
        return True
    except Exception as e:
        if note:
            try:
                await ctx.client.edit_message(event.chat_id, note.id,
                                              f"❌ خطا: {e.__class__.__name__} — {e}")
            except Exception:
                pass
        else:
            try:
                await ctx.reply(event, "❌ از این لینک چیزی نیامد — لینک پست کامل است؟")
            except Exception:
                pass
        return False


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
            path = await src.download_media(file=tmp_path(media_ext(src)))
            caption = f"💾 ذخیره‌شده از {getattr(event.chat, 'title', None) or 'چت'}"
            await ctx.client.send_file(ctx.relay_chat(), path, caption=caption)
            os.remove(path)
            await ctx.client.edit_message(event.chat_id, note.id, "✅ ذخیره شد")
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ خطا: {e}")

    # ---------- سیو از لینک t.me — چنل‌های فوروارد‌بسته ----------
    @bot.cmd("سیو لینک", "سیو مدیا از این چنل", "savelink", cat="مدیا",
             help="سیو لینک <لینک t.me> — پست چنل‌هایی که فورواردشان بسته است: لینک پست را بده "
                  "یا روی پیامی که لینک دارد ریپلی کن (آلبوم + لینک خصوصی t.me/c/...). "
                  "حالت خودکار: «سیو لینک خودکار روشن»")
    async def _save_link(event, ctx, args):
        a = (args or "").strip()
        ls = ctx.acc.setdefault("linksave", {"on": False})
        if a.startswith("خودکار") or a.lower().startswith("auto"):
            rest = (a[6:] if a.startswith("خودکار") else a[4:]).strip().lower()
            if rest in ("روشن", "on", "فعال"):
                ls["on"] = True
                ctx.store.save()
                return await ctx.reply(
                    event, "🟢 سیو خودکار لینک روشن شد\n"
                           "توی سیو مسیج فقط لینک پست را بفرست — "
                           "عکس/ویدیو/ویسش خودکار با فرمت واقعی می‌آید")
            if rest in ("خاموش", "off", "غیرفعال"):
                ls["on"] = False
                ctx.store.save()
                return await ctx.reply(event, "🔴 سیو خودکار لینک خاموش شد")
            st = "روشن ✅" if ls.get("on") else "خاموش ⛔"
            return await ctx.reply(
                event, f"ℹ️ سیو خودکار لینک: {st}\n"
                       "روشن: «سیو لینک خودکار روشن» | خاموش: «سیو لینک خودکار خاموش»")
        link = a
        src = await event.get_reply_message() if event.is_reply else None
        if not link and src and src.raw_text:
            link = src.raw_text
        hit = None
        for m in _TME_RE.finditer(link or ""):
            if parse_tme_link(m.group(0)):
                hit = m.group(0)
                break
        if not hit:
            return await ctx.reply(
                event, "❗ لینک پست را بده:\n"
                       "«سیو لینک https://t.me/چنل/123» یا روی پیامی که لینک دارد ریپلی کن\n"
                       "لینک خصوصی t.me/c/... هم کار می‌کند | خودکار: «سیو لینک خودکار روشن»")
        note = await ctx.reply(event, "⏳ در حال درآوردن پست...")
        await _do_save_link(event, ctx, hit,
                            src.id if src else event.message.id, note)

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
                    path = await ctx.client.download_media(s.media, file=tmp_path(media_ext(s.media)))
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
                    path = await msg.download_media(file=tmp_path(media_ext(msg)))
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
            path = await msg.download_media(file=tmp_path(media_ext(msg)))
            if path:
                await ctx.client.send_file(
                    dest, path,
                    caption="⏲ مدیای زمان‌دار (قبل از حذف شدن ذخیره شد)")
                os.remove(path)
        except Exception:
            pass

    @bot.msg_hook
    async def _link_auto(event, ctx):
        """سیو خودکار لینک: توی سیو مسیج، هر پیامِ خودت که لینک t.me پست دارد
        (و دستور نیست) خودش مدیای پست را می‌آورد — بدون ریپلی."""
        msg = event.message
        if not msg or not msg.out or not msg.raw_text:
            return
        try:
            if str(event.chat_id) != str(ctx.me_id):
                return  # فقط سیو مسیج
        except Exception:
            return
        if msg.id in ctx.extra.get("ls_skip", ()):
            return
        txt = msg.raw_text.strip()
        if not txt:
            return
        if txt.split()[0].lower() in ("سیو", "ذخیره", "save", "savelink", "دریافت"):
            return  # دستور است نه لینک
        if msg.media and "💾 سیو از" in txt[:60]:
            return  # خروجی خودمان — حلقه نشود
        ls = ctx.acc.setdefault("linksave", {"on": False})
        if not ls.get("on"):
            return
        for m in _TME_RE.finditer(txt):
            if parse_tme_link(m.group(0)):
                try:
                    await _do_save_link(event, ctx, m.group(0), msg.id)
                except Exception:
                    pass
                break
