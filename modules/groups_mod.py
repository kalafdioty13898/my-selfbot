# -*- coding: utf-8 -*-
"""ماژول گروه: قفل عنوان/عکس، سکوت، فیلتر، تگ، پاکسازی، خوش‌آمدگویی، اخراج و ..."""
import asyncio
import os
import time

from telethon.tl import functions, types
from telethon.errors import ChatAdminRequiredError
from telethon.tl.types import (ChannelParticipantsAdmins, InputChatUploadedPhoto)

from framework import Bot
from utils import get_user, render_vars, tmp_path


def _chat_key(cid):
    return str(cid)


def setup(bot: Bot):
    tag_active = {}  # chat_id -> bool
    watch_state = {"n": 0}  # شمارنده تیک برای نرم‌کردن چک قفل‌ها

    # ================= قفل عنوان / عکس =================
    @bot.cmd("قفل عنوان روشن", "locktitle", cat="گروه",
             help="قفل عنوان روشن — عنوان گروه قفل شود (فقط تو بتونی عوض کنی)")
    async def _lock_title_on(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ این دستور مال گروه است")
        entity = await event.get_chat()
        ctx.acc["lock"][_chat_key(event.chat_id)] = {
            "title": entity.title or "", "photo_msg": None, "base_photo_id": None,
            "title_on": True, "photo_on": False}
        ctx.store.save()
        await ctx.reply(event, f"🔒 عنوان قفل شد: «{entity.title}»")

    @bot.cmd("قفل عنوان خاموش", "unlocktitle", cat="گروه",
             help="قفل عنوان خاموش — آزاد کردن عنوان")
    async def _lock_title_off(event, ctx, args):
        ctx.acc["lock"].get(_chat_key(event.chat_id), {})["title_on"] = False
        ctx.store.save()
        await ctx.reply(event, "🔓 قفل عنوان برداشته شد")

    @bot.cmd("قفل عکس روشن", "lockphoto", cat="گروه",
             help="قفل عکس روشن — عکس گروه قفل شود (سوپرگروه)")
    async def _lock_photo_on(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ این دستور مال گروه است")
        lock = ctx.acc["lock"].setdefault(_chat_key(event.chat_id),
                                          {"title": "", "title_on": False, "photo_on": False})
        entity = await event.get_chat()
        # عکس فعلی را در چت ذخیره نگه می‌داریم
        photo = entity.photo
        photo_msg = None
        if photo:
            try:
                path = await ctx.client.download_media(photo, file=tmp_path("gp"))
                photo_msg = await ctx.client.send_file(ctx.relay_chat(), path,
                                                       caption="locked_group_photo")
                os.remove(path)
            except Exception:
                pass
        lock["photo_msg"] = photo_msg.id if photo_msg else None
        lock["base_photo_id"] = getattr(photo, "id", None)  # عکس فعلی به‌عنوان مبنا
        lock["photo_on"] = True
        ctx.store.save()
        await ctx.reply(event, "🔒 عکس گروه قفل شد")

    @bot.cmd("قفل عکس خاموش", "unlockphoto", cat="گروه",
             help="قفل عکس خاموش — آزاد کردن عکس گروه")
    async def _lock_photo_off(event, ctx, args):
        ctx.acc["lock"].get(_chat_key(event.chat_id), {})["photo_on"] = False
        ctx.store.save()
        await ctx.reply(event, "🔓 قفل عکس برداشته شد")

    @bot.tick_hook
    async def _watch_locks(ctx):
        locks = ctx.acc["lock"]
        if not locks:
            return
        # هر تیک (۲۰ ثانیه) نه — هر ۱۰ تیک (~۳٫۳ دقیقه) یک‌بار؛ وگرنه فلود تلگرام می‌گیریم
        watch_state["n"] += 1
        if watch_state["n"] % 10 != 1:
            return
        for cid, lock in list(locks.items()):
            try:
                chat_id = int(cid)
                entity = await ctx.client.get_entity(chat_id)
                if isinstance(entity, types.Chat):
                    # گروه معمولی — فقط قفل عنوان (عکس گروه معمولی ساپورت نیست)
                    if lock.get("title_on") and lock.get("title") and entity.title != lock["title"]:
                        try:
                            await ctx.client(functions.messages.EditChatTitleRequest(
                                await ctx.client.get_input_entity(chat_id), lock["title"]))
                        except ChatAdminRequiredError:
                            pass
                    continue
                if not isinstance(entity, types.Channel):
                    continue
                if lock.get("title_on") and lock.get("title") and entity.title != lock["title"]:
                    try:
                        await ctx.client(functions.channels.EditTitleRequest(chat_id, lock["title"]))
                    except ChatAdminRequiredError:
                        pass
                if lock.get("photo_on") and lock.get("photo_msg"):
                    full = await ctx.client(functions.channels.GetFullChannelRequest(chat_id))
                    cur = full.full_chat.chat_photo
                    cur_id = getattr(cur, "id", None)
                    base_id = lock.get("base_photo_id")
                    if base_id and cur_id and cur_id != base_id:
                        # عکس عوض شده — برگردان به عکس ذخیره‌شده
                        msgs = await ctx.client.get_messages(ctx.relay_chat(), ids=[lock["photo_msg"]])
                        m0 = msgs[0] if msgs else None
                        if m0 and m0.media:
                            path = await m0.download_media(file=tmp_path("gp2"))
                            uploaded = await ctx.client.upload_file(path)
                            await ctx.client(functions.channels.EditPhotoRequest(
                                chat_id, InputChatUploadedPhoto(file=uploaded)))
                            os.remove(path)
                            full2 = await ctx.client(functions.channels.GetFullChannelRequest(chat_id))
                            lock["base_photo_id"] = getattr(full2.full_chat.chat_photo, "id", None)
                            ctx.store.save()
                    elif cur_id and not base_id:
                        lock["base_photo_id"] = cur_id
                        ctx.store.save()
            except Exception:
                continue

    # ================= سکوت (گروه + پیوی) =================
    @bot.cmd("سکوت روشن", "muteon", cat="گروه",
             help="سکوت روشن — همه (به‌جز ادمین‌ها و تو) پیامشان حذف شود؛ در پیوی هم کار می‌کند (پیام‌های طرف حذف شود)")
    async def _mute_on(event, ctx, args):
        ctx.acc["mute"][_chat_key(event.chat_id)] = {"on": True, "until": 0}
        ctx.store.save()
        where = ("این پیوی — پیام‌های طرف مقابل خودکار حذف می‌شود"
                 if event.is_private else "گروه — پیام همه به‌جز ادمین‌ها حذف می‌شود")
        await ctx.reply(event, f"🔇 {where} ساکت شد")

    @bot.cmd("سکوت خاموش", "muteoff", cat="گروه",
             help="سکوت خاموش — پایان سکوت گروه یا پیوی")
    async def _mute_off(event, ctx, args):
        ctx.acc["mute"].pop(_chat_key(event.chat_id), None)
        ctx.store.save()
        await ctx.reply(event, "🔊 سکوت برداشته شد")

    @bot.cmd("سکوت همه", "muteall", cat="گروه",
             help="سکوت همه <ثانیه> — سکوت موقت (گروه/پیوی)، مثلا: سکوت همه 30")
    async def _mute_all(event, ctx, args):
        try:
            sec = int(args.strip())
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: سکوت همه 30")
        ctx.acc["mute"][_chat_key(event.chat_id)] = {"on": True, "until": time.time() + sec}
        ctx.store.save()
        where = "این پیوی" if event.is_private else "گروه"
        await ctx.reply(event, f"🔇 {where} {sec} ثانیه ساکت شد")

    @bot.cmd("لغو سکوت همه", "unmuteall", cat="گروه",
             help="لغو سکوت همه — پایان سکوت موقت")
    async def _unmute_all(event, ctx, args):
        ctx.acc["mute"].pop(_chat_key(event.chat_id), None)
        ctx.store.save()
        await ctx.reply(event, "🔊 سکوت موقت لغو شد")

    # ================= قفل مدیا (گروه + پیوی) =================
    LOCK_TYPES = [
        ("استیکر", "locksticker", lambda m: bool(m.sticker)),
        ("وویس", "lockvoice", lambda m: bool(m.voice)),
        ("گیف", "lockgif", lambda m: bool(m.gif)),
        ("فیلم", "lockvideo", lambda m: bool(m.video or m.video_note)),
        ("موزیک", "lockmusic", lambda m: bool(m.audio) and not bool(m.voice)),
    ]

    def _mlock_cfg(ctx, event):
        """تنظیم قفل مدیا برای همین چت (پیوی = تنظیم سراسری پیوی)."""
        ml = ctx.acc["mlock"]
        k = "pv" if event.is_private else _chat_key(event.chat_id)
        return ml.setdefault(k, {}), k

    def _make_lock(name, on):
        async def _lock(event, ctx, args):
            cfg, k = _mlock_cfg(ctx, event)
            cfg[name] = on
            ctx.store.save()
            where = "پیوی (همه پیوی‌ها)" if event.is_private else "این گروه"
            icon = "🔒" if on else "🔓"
            return await ctx.reply(event, f"{icon} قفل {name} در {where} "
                                          f"{'روشن شد' if on else 'برداشته شد'}")
        return _lock

    for _name, _en, _matcher in LOCK_TYPES:
        bot.cmd(f"قفل {_name} روشن", _en, cat="گروه",
                help=f"قفل {_name} روشن — {_name} ممنوع؛ در گروه اعضا و در پیوی همه حذف می‌شود "
                     "(پیوی = همه پیوی‌ها)")(_make_lock(_name, True))
        bot.cmd(f"قفل {_name} خاموش", _en + "off", cat="گروه",
                help=f"قفل {_name} خاموش — آزاد کردن {_name}")(_make_lock(_name, False))

    @bot.cmd("قفل ها", "locks", cat="گروه",
             help="قفل ها — وضعیت قفل مدیا در این چت (و پیوی)")
    async def _locks_status(event, ctx, args):
        pv = ctx.acc["mlock"].get("pv", {})
        chat = {} if event.is_private else ctx.acc["mlock"].get(_chat_key(event.chat_id), {})
        lines = []
        for name, _en, _m in LOCK_TYPES:
            lines.append(f"• {name}: پیوی {'🔒' if pv.get(name) else '🔓'} | "
                         f"این چت {'🔒' if chat.get(name) else '🔓'}")
        await ctx.reply(event, "🔐 قفل‌های مدیا:\n" + "\n".join(lines)
                        + "\n(پیوی = همه پیوی‌ها)")

    async def _media_locked(ctx, msg, cfg):
        """True اگر مدیای پیام قفل باشد."""
        if not cfg:
            return False
        for _name, _en, matcher in LOCK_TYPES:
            if cfg.get(_name):
                try:
                    if matcher(msg):
                        return True
                except Exception:
                    continue
        return False

    # ================= فیلتر کلمات =================
    @bot.cmd("فیلتر کردن", "filter", cat="گروه",
             help="فیلتر کردن <کلمه> — پیام حاوی کلمه حذف شود (در گروه و پیوی؛ چند خطی هم میشه)")
    async def _filter_add(event, ctx, args):
        words = [w.strip() for w in (args or "").splitlines() if w.strip()]
        if not words:
            return await ctx.reply(event, "❗ کلمه را جلوی دستور بنویس")
        f = ctx.acc["filters"].setdefault(_chat_key(event.chat_id), {"words": [], "allow": []})
        f["words"] = list(set(f["words"] + words))
        ctx.store.save()
        await ctx.reply(event, f"🚫 {len(words)} کلمه فیلتر شد")

    @bot.cmd("حذف فیلتر", "unfilter", cat="گروه",
             help="حذف فیلتر <کلمه> — برداشتن یک کلمه از فیلتر")
    async def _filter_del(event, ctx, args):
        w = (args or "").strip()
        f = ctx.acc["filters"].get(_chat_key(event.chat_id))
        if f and w in f["words"]:
            f["words"].remove(w)
            ctx.store.save()
            return await ctx.reply(event, "✅ از فیلتر حذف شد")
        await ctx.reply(event, "❗ چنین کلمه‌ای در فیلتر نیست")

    @bot.cmd("لیست فیلتر", "filters", cat="گروه",
             help="لیست فیلتر — نمایش کلمات فیلترشده این گروه")
    async def _filter_list(event, ctx, args):
        f = ctx.acc["filters"].get(_chat_key(event.chat_id))
        if not f or not f["words"]:
            return await ctx.reply(event, "ℹ️ فیلتری برای این گروه نیست")
        await ctx.reply(event, "🚫 فیلترها:\n• " + "\n• ".join(f["words"]))

    @bot.cmd("پاکسازی لیست فیلتر", "filterclean", cat="گروه",
             help="پاکسازی لیست فیلتر — حذف همه فیلترهای این گروه")
    async def _filter_clean(event, ctx, args):
        ctx.acc["filters"].pop(_chat_key(event.chat_id), None)
        ctx.store.save()
        await ctx.reply(event, "♻️ لیست فیلتر این گروه پاک شد")

    # ================= تگ =================
    @bot.cmd("تگ", "tag", cat="گروه",
             help="تگ [متن] — تگ همه اعضا (لغو با: لغو تگ)")
    async def _tag(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ این دستور مال گروه است")
        text = (args or "").strip()
        tag_active[event.chat_id] = True
        await _do_tag(event, ctx, "all", text)

    @bot.cmd("تگ مدیران", "tagadmin", cat="گروه",
             help="تگ مدیران [متن] — تگ فقط ادمین‌ها")
    async def _tag_admins(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ این دستور مال گروه است")
        text = (args or "").strip()
        tag_active[event.chat_id] = True
        await _do_tag(event, ctx, "admins", text)

    @bot.cmd("لغو تگ", "untag", cat="گروه",
             help="لغو تگ — توقف تگ در حال اجرا")
    async def _tag_cancel(event, ctx, args):
        tag_active[event.chat_id] = False
        await ctx.reply(event, "✋ تگ متوقف شد")

    async def _do_tag(event, ctx, mode, text):
        note = await ctx.reply(event, "🔄 در حال تگ...")
        try:
            if mode == "admins":
                users = [p async for p in ctx.client.iter_participants(
                    event.chat_id, filter=ChannelParticipantsAdmins())]
            else:
                users = [p async for p in ctx.client.iter_participants(event.chat_id)]
        except Exception as e:
            return await ctx.client.edit_message(event.chat_id, note.id, f"❌ {e}")
        chunk, chunks = [], []
        for u in users:
            if getattr(u, "bot", False) and mode == "all":
                continue
            name = ((u.first_name or "") or "کاربر").replace("<", "")
            chunk.append(f"<a href='tg://user?id={u.id}'>{name}</a>")
            if len(chunk) >= 8:
                chunks.append(chunk)
                chunk = []
        if chunk:
            chunks.append(chunk)
        sent = 0
        for c in chunks:
            if not tag_active.get(event.chat_id, False):
                break
            body = (text + "\n\n" if text else "") + " ، ".join(c)
            await ctx.client.send_message(event.chat_id, body, parse_mode="html")
            sent += len(c)
            await asyncio.sleep(3)
        tag_active[event.chat_id] = False
        await ctx.client.edit_message(event.chat_id, note.id, f"✅ {sent} نفر تگ شد")

    # ================= پاکسازی =================
    TYPE_FILTERS = {
        "عکس ها": lambda m: bool(m.photo),
        "ویدئو ها": lambda m: bool(m.video),
        "ویس ها": lambda m: bool(m.voice),
        "فایل ها": lambda m: bool(m.document) and not (m.video or m.voice or m.audio or m.gif),
        "گیف ها": lambda m: bool(m.gif),
        "اهنگ ها": lambda m: bool(m.audio),
        "پیام ها": lambda m: True,
    }

    def _make_clean(matcher):
        async def _clean(event, ctx, args):
            if not event.is_group and not event.is_private:
                return await ctx.reply(event, "❗ این دستور اینجا کار نمی‌کنه")
            note = await ctx.reply(event, "🧹 در حال پاکسازی...")
            ids = []
            count = 0
            try:
                async for m in ctx.client.iter_messages(event.chat_id, limit=3000):
                    if matcher(m):
                        ids.append(m.id)
                    if len(ids) >= 100:
                        await ctx.client.delete_messages(event.chat_id, ids)
                        count += len(ids)
                        ids = []
                if ids:
                    await ctx.client.delete_messages(event.chat_id, ids)
                    count += len(ids)
                await ctx.client.edit_message(event.chat_id, note.id, f"🧹 {count} پیام پاک شد")
            except ChatAdminRequiredError:
                await ctx.client.edit_message(event.chat_id, note.id,
                                              "❌ دسترسی حذف پیام دیگران را ندارم")
            except Exception as e:
                await ctx.client.edit_message(event.chat_id, note.id, f"❌ {e}")
        return _clean

    for key, matcher in TYPE_FILTERS.items():
        en = {"عکس ها": "cleanphoto", "ویدئو ها": "cleanvideo", "ویس ها": "cleanvoice",
              "فایل ها": "cleanfile", "گیف ها": "cleangif", "اهنگ ها": "cleanaudio",
              "پیام ها": "cleanall"}[key]
        bot.cmd(f"پاکسازی {key}", en, cat="گروه",
                help=f"پاکسازی {key} — حذف پیام‌های {key} (تا ۳۰۰۰ پیام اخیر)")(
            _make_clean(matcher))

    @bot.cmd("حذف", "deln", cat="گروه",
             help="حذف <عدد> — حذف آخرین پیام‌های خودت، مثلا: حذف 10")
    async def _del_mine(event, ctx, args):
        try:
            n = min(int(args.strip() or "1"), 500)
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: حذف 10")
        ids = []
        async for m in ctx.client.iter_messages(event.chat_id, from_user="me", limit=n):
            ids.append(m.id)
        await ctx.client.delete_messages(event.chat_id, ids)
        await ctx.reply(event, f"🗑 {len(ids)} پیام حذف شد")

    # ================= خوش‌آمدگویی =================
    @bot.cmd("تنظیم خوش امدگویی", "setwelcome", cat="گروه",
             help="تنظیم خوش امدگویی (ریپلی) — پیام خوش‌آمد تنظیم شود")
    async def _set_welcome(event, ctx, args):
        if args:
            t = args
        elif event.is_reply:
            m = await event.get_reply_message()
            t = m.raw_text or ""
        else:
            return await ctx.reply(event, "❗ روی متن ریپلی کن یا جلوی دستور بنویس")
        ctx.acc["welcome"][_chat_key(event.chat_id)] = {"on": True, "text": t}
        ctx.store.save()
        await ctx.reply(event, "✅ پیام خوش‌آمد ذخیره شد (متغیر NAME و USERNAME کار می‌کند)")

    @bot.cmd("خوش امدگویی روشن", "welcomeon", cat="گروه",
             help="خوش امدگویی روشن — ارسال پیام برای عضو جدید")
    async def _welcome_on(event, ctx, args):
        w = ctx.acc["welcome"].setdefault(
            _chat_key(event.chat_id), {"on": False, "text": ""})
        if not w["text"]:
            return await ctx.reply(event, "❗ اول پیام را تنظیم کن (تنظیم خوش امدگویی)")
        w["on"] = True
        ctx.store.save()
        await ctx.reply(event, "✅ خوش‌آمدگویی روشن شد")

    @bot.cmd("خوش امدگویی خاموش", "welcomeoff", cat="گروه",
             help="خوش امدگویی خاموش — قطع پیام خوش‌آمد")
    async def _welcome_off(event, ctx, args):
        w = ctx.acc["welcome"].get(_chat_key(event.chat_id))
        if w:
            w["on"] = False
            ctx.store.save()
        await ctx.reply(event, "✅ خوش‌آمدگویی خاموش شد")

    @bot.action_hook
    async def _on_join(event, ctx):
        try:
            if ctx.bot_off(event.chat_id):
                return  # سلف در این چت خاموش است
            w = ctx.acc["welcome"].get(_chat_key(event.chat_id))
            if not w or not w.get("on") or not w.get("text"):
                return
            user = None
            if event.user_joined and event.user:
                user = event.user
            elif event.user_added and event.users:
                user = [u for u in event.users if u.id != ctx.me_id]
                user = user[0] if user else None
            if not user:
                return
            await ctx.client.send_message(event.chat_id,
                                          render_vars(w["text"], ctx.cfg.tz, user=user))
        except Exception:
            pass

    # ================= اخراج / اطلاعات =================
    @bot.cmd("اخراج", "kick", cat="گروه",
             help="اخراج <user> (یا ریپلی) — حذف کاربر از گروه")
    async def _kick(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ این دستور مال گروه است")
        u = await get_user(ctx.client, event, args)
        if not u:
            return await ctx.reply(event, "❗ ریپلی کن یا آیدی/یوزرنیم بده")
        try:
            await ctx.client.kick_participant(event.chat_id, u.id)
            await ctx.reply(event, f"👢 <a href='tg://user?id={u.id}'>کاربر</a> اخراج شد",
                            parse_mode="html")
        except Exception as e:
            await ctx.reply(event, f"❌ نشد: {e.__class__.__name__}")

    @bot.cmd("لینک گروه", "grouplink", cat="گروه",
             help="لینک گروه — دریافت لینک دعوت")
    async def _glink(event, ctx, args):
        try:
            link = await ctx.client(functions.messages.ExportChatInviteRequest(event.chat_id))
            await ctx.reply(event, f"🔗 {link.link}")
        except Exception as e:
            await ctx.reply(event, f"❌ {e.__class__.__name__}")

    @bot.cmd("شناسه گروه", "chatid", cat="گروه",
             help="شناسه گروه — نمایش شناسه عددی این چت")
    async def _cid(event, ctx, args):
        await ctx.reply(event, f"🆔 <code>{event.chat_id}</code>", parse_mode="html")

    @bot.cmd("درباره گروه", "groupinfo", cat="گروه",
             help="درباره گروه — اطلاعات کامل گروه")
    async def _ginfo(event, ctx, args):
        try:
            entity = await event.get_chat()
            full = await ctx.client(functions.channels.GetFullChannelRequest(event.chat_id)) \
                if isinstance(entity, types.Channel) else None
            members = getattr(getattr(full, "full_chat", None), "participants_count", "?")
            await ctx.reply(event,
                            f"ℹ️ <b>{entity.title}</b>\n"
                            f"🆔 <code>{event.chat_id}</code>\n"
                            f"👥 اعضا: {members}\n"
                            f"🔒 نوع: {'سوپرگروه' if isinstance(entity, types.Channel) else 'گروه معمولی'}",
                            parse_mode="html")
        except Exception as e:
            await ctx.reply(event, f"❌ {e.__class__.__name__}")

    # ================= هوک مدریتی پیام‌های گروه + پیوی =================
    async def _safe_del(msg):
        try:
            await msg.delete()
        except Exception:
            pass

    def _mute_active(ctx, cid):
        """سکوت این چت فعاله؟ سکوت موقت منقضی‌شده را هم پاک می‌کند."""
        mute = ctx.acc["mute"].get(cid)
        if not (mute and mute.get("on")):
            return False
        if mute.get("until") and time.time() > mute["until"]:
            ctx.acc["mute"].pop(cid, None)
            ctx.store.save()
            return False
        return True

    async def _apply_filters(ctx, msg, cid):
        """فیلتر کلمات — خروجی True یعنی پیام حذف شد."""
        f = ctx.acc["filters"].get(cid)
        if not f:
            return False
        text = (msg.raw_text or "").lower()
        if any(w.lower() in text for w in f["words"]):
            await _safe_del(msg)
            return True
        if f["allow"] and not any(w.lower() in text for w in f["allow"]):
            await _safe_del(msg)
            return True
        return False

    mute_log_ts = {}  # chat_key -> آخرین لاگ سکوت (ضد اسپم؛ حداکثر هر ۱۰ ثانیه)

    async def _log_mute(ctx, event, msg):
        now = time.time()
        k = _chat_key(event.chat_id)
        if now - mute_log_ts.get(k, 0) < 10:
            return
        mute_log_ts[k] = now
        who = getattr(msg.sender, "first_name", None) or "ناشناس"
        uid = msg.sender_id or "?"
        where = "پیوی" if event.is_private else "گروه"
        try:
            await ctx.send(ctx.relay_chat(),
                           f"🔇 سکوت {where}: پیام {who} (<code>{uid}</code>) حذف شد",
                           parse_mode="html")
        except Exception:
            pass

    @bot.msg_hook
    async def _moderate(event, ctx):
        msg = event.message
        if msg.out or msg.action:
            return
        uid = msg.sender_id
        if not uid or uid == 777000:
            return
        cid = _chat_key(event.chat_id)

        # 🔇 سکوت «مطلق» است و قبل از همه معافیت‌ها چک می‌شود.
        # باگ قبلی: فرستندهٔ سودو/لیست‌سیاه/ربات قبل از سکوت رد می‌شد و
        # پیام‌هایش هرگز حذف نمی‌شد (مخصوصاً وقتی با اکانت دومِ سودو تست می‌شد).
        # فقط ادمین‌های گروه معاف‌اند؛ پیام‌های 777000 (تلگرام) هرگز حذف نمی‌شوند.
        if _mute_active(ctx, cid):
            admin_free = False
            if not event.is_private:
                try:
                    admin_free = await ctx.admins.is_admin(ctx.client, event.chat_id, uid)
                except Exception:
                    admin_free = False
            if not admin_free:
                await _safe_del(msg)
                await _log_mute(ctx, event, msg)
                return

        if ctx.is_sudo(uid) or uid in ctx.acc["black"] or getattr(msg.sender, "bot", False):
            return

        if event.is_private:
            # فیلتر/قفل مدیای پیوی — معافیت سودو فقط برای این‌ها معنا دارد
            if await _apply_filters(ctx, msg, cid):
                return
            # قفل مدیا در پیوی: قفل پیوی سراسری
            if await _media_locked(ctx, msg, ctx.acc["mlock"].get("pv")):
                await _safe_del(msg)
            return
        if not event.is_group:
            return
        try:
            if await ctx.admins.is_admin(ctx.client, event.chat_id, uid):
                return
        except Exception:
            return
        if await _apply_filters(ctx, msg, cid):
            return
        # قفل مدیا گروه: فقط اعضای عادی (ادمین‌ها آزادند)
        if await _media_locked(ctx, msg, ctx.acc["mlock"].get(cid)):
            await _safe_del(msg)
