# -*- coding: utf-8 -*-
"""ماژول منشی: ریپلای خودکار پیوی + پاسخ افلاین مستقل (متن/مدیا) + شیفت کاری
+ تایپ جادویی + لیست سیاه.

منطق افلاین (بازطراحی طبق درخواست کاربر):
- «تنظیم منشی افلاین» روی هر پیامی ریپلی کن → همان پیام (متن یا مدیا) ذخیره می‌شود.
- به‌محض اینکه اکانت X دقیقه (پیش‌فرض ۵) هیچ فعالیتی (پیام خروجی) نداشته باشد،
  هرکس پیوی بدهد همان پیام برایش ارسال می‌شود.
- وقتی دوباره پیام بدهی (فعال شدی) پاسخ افلاین قطع می‌شود — بدون دستور اضافه.
"""
import time

from telethon.tl import types

from framework import Bot
from storage import norm_sec
from utils import in_shift, render_vars, typing_then

AWAY_DEFAULT = "🕐 خارج از ساعت کاری‌ام — بعداً پیام بده 🙏"


def setup(bot: Bot):
    last_reply = {}  # user_id -> ts

    # ---------- روشن/خاموش و تنظیم پیام معمولی ----------
    @bot.cmd("منشی روشن", "secon", cat="منشی",
             help="منشی روشن — ریپلای خودکار پیوی فعال شود")
    async def _on(event, ctx, args):
        norm_sec(ctx.acc["sec"])
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event, "🤖 منشی روشن شد" + ("" if ctx.acc["sec"]["text"] else
                                                    "\n⚠️ هنوز پیامی تنظیم نکردی: روی متن ریپلی کن و بزن «تنظیم منشی»"))

    @bot.cmd("منشی خاموش", "secoff", cat="منشی",
             help="منشی خاموش — ریپلای خودکار خاموش شود")
    async def _off(event, ctx, args):
        ctx.acc["sec"]["on"] = False
        ctx.store.save()
        await ctx.reply(event, "🤖 منشی خاموش شد")

    @bot.cmd("تنظیم منشی", "setsec", cat="منشی",
             help="تنظیم منشی (ریپلی روی متن) — پیام منشی تنظیم شود")
    async def _set(event, ctx, args):
        if args:
            ctx.acc["sec"]["text"] = args
        elif event.is_reply:
            m = await event.get_reply_message()
            ctx.acc["sec"]["text"] = m.raw_text or ""
        else:
            return await ctx.reply(event, "❗ روی متن ریپلی کن یا جلوی دستور بنویس")
        ctx.store.save()
        await ctx.reply(event, "✅ پیام منشی ذخیره شد")

    @bot.cmd("وضعیت منشی", "secstatus", cat="منشی",
             help="وضعیت منشی — پیام و حالت فعلی منشی")
    async def _st(event, ctx, args):
        s = norm_sec(ctx.acc["sec"])
        om = s.get("off_msg")
        off_desc = "مدیا" if (om and om.get("type") == "media") else ((om or {}).get("content") or "—")
        sh = s.get("shift")
        sh_desc = (f"{sh['from'] // 60:02d}:{sh['from'] % 60:02d} تا "
                   f"{sh['to'] // 60:02d}:{sh['to'] % 60:02d}") if sh else "—"
        await ctx.reply(event,
                        f"🤖 منشی: {'✅ روشن' if s['on'] else '❌ خاموش'} | حالت: {s['mode']} | "
                        f"فاصله جواب: {s['cool']} دقیقه\n"
                        f"😴 پاسخ افلاین: {'✅ روشن' if s.get('off_on') else '❌ خاموش'} | "
                        f"آستانه: {s['offline_min']} دقیقه | پیام: {off_desc}\n"
                        f"🕘 شیفت کاری: {sh_desc}\n"
                        f"⌨️ تایپ جادویی: {'✅ روشن' if s.get('typing', True) else '❌ خاموش'} | "
                        f"🏷 جواب منشن گروه: {'✅' if s.get('tag') else '❌'}\n"
                        f"💬 پیام منشی: {s['text'] or '—'}")

    @bot.cmd("منشی هوشمند روشن", "secsmart", cat="منشی",
             help="منشی هوشمند روشن — فقط به بار اولی که پیام می‌دهد جواب بدهد")
    async def _smart(event, ctx, args):
        norm_sec(ctx.acc["sec"])
        ctx.acc["sec"]["mode"] = "smart"
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event, "🧠 حالت هوشمند فعال شد (فقط پیام‌دهی جدید جواب می‌گیرند)")

    @bot.cmd("منشی آنی روشن", "secnow", cat="منشی",
             help="منشی آنی روشن — بلافاصله و همیشه به پیوی جواب بدهد (حتی وقتی آنلاینی)")
    async def _now(event, ctx, args):
        norm_sec(ctx.acc["sec"])
        ctx.acc["sec"]["mode"] = "all"
        ctx.acc["sec"]["on"] = True
        ctx.store.save()
        await ctx.reply(event,
                        "⚡ حالت آنی فعال شد: هر پیام خصوصی فوری جواب می‌گیرد\n"
                        f"⏳ فاصله جواب هر کاربر: {ctx.acc['sec']['cool']} دقیقه "
                        "(تغییر: تنظیم زمان منشی 2)")

    # ---------- پاسخ افلاین (بازطراحی‌شده) ----------
    @bot.cmd("تنظیم منشی افلاین", "setsecoff", cat="منشی",
             help="تنظیم منشی افلاین (ریپلی) — روی هر متن/مدیایی ریپلی کن؛ "
                  "همین پیام بعد از خروجت به پیام‌دهنده‌های پیوی ارسال می‌شود")
    async def _set_off_msg(event, ctx, args):
        s = norm_sec(ctx.acc["sec"])
        if event.is_reply:
            m = await event.get_reply_message()
            if m and m.media and (m.raw_text is not None or m.sticker or m.voice or m.photo):
                # مدیا: کپی در چت ذخیره‌سازی تا بعد از حذف پیام اصلی هم باقی بماند
                dest = ctx.relay_chat()
                try:
                    fwd = await ctx.client.forward_messages(dest, event.chat_id, m.id)
                except Exception:
                    return await ctx.reply(event, "❌ کپی مدیا ممکن نشد (چت ذخیره‌سازی را چک کن)")
                s["off_msg"] = {"type": "media", "chat": dest, "msg": fwd.id}
            else:
                s["off_msg"] = {"type": "text", "content": m.raw_text or ""}
        elif args:
            s["off_msg"] = {"type": "text", "content": args}
        else:
            return await ctx.reply(event, "❗ روی پیام موردنظر ریپلی کن یا متن را جلوی دستور بنویس")
        s["off_on"] = True  # همان لحظه مسلح شود
        ctx.store.save()
        await ctx.reply(event,
                        "✅ پیام افلاین ذخیره و فعال شد\n"
                        f"⏱ بعد از {s['offline_min']} دقیقه بی‌فعالیتی، هرکس پیوی بدهد همین پیام را می‌گیرد\n"
                        "📏 آستانه: زمان منشی افلاین 10 | خاموش: منشی افلاین خاموش")

    @bot.cmd("منشی افلاین روشن", "secoffon", cat="منشی",
             help="منشی افلاین روشن — پاسخ افلاین فعال شود (اول پیامش را تنظیم کن)")
    async def _off_on(event, ctx, args):
        s = norm_sec(ctx.acc["sec"])
        if not s.get("off_msg"):
            return await ctx.reply(event,
                                   "❗ اول پیام افلاین را تنظیم کن: روی پیام ریپلی کن و بزن «تنظیم منشی افلاین»")
        s["off_on"] = True
        ctx.store.save()
        await ctx.reply(event, f"😴 پاسخ افلاین روشن شد (بعد از {s['offline_min']} دقیقه بی‌فعالیتی)")

    @bot.cmd("منشی افلاین خاموش", "secoffoff", cat="منشی",
             help="منشی افلاین خاموش — پاسخ افلاین قطع شود")
    async def _off_off(event, ctx, args):
        s = norm_sec(ctx.acc["sec"])
        s["off_on"] = False
        ctx.store.save()
        await ctx.reply(event, "😴 پاسخ افلاین خاموش شد")

    @bot.cmd("زمان منشی افلاین", "secoffmin", cat="منشی",
             help="زمان منشی افلاین <دقیقه> — چند دقیقه بی‌فعالیتی = افلاین (پیش‌فرض 5)")
    async def _offmin(event, ctx, args):
        try:
            v = max(1, int((args or "").strip()))
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: زمان منشی افلاین 10")
        norm_sec(ctx.acc["sec"])["offline_min"] = v
        ctx.store.save()
        await ctx.reply(event, f"✅ آستانه افلاین: {v} دقیقه")

    # ---------- شیفت کاری ----------
    @bot.cmd("شیفت منشی", "secshift", cat="منشی",
             help="شیفت منشی 9 تا 18 — منشی فقط در این ساعت‌ها جواب بدهد و بیرون شیفت "
                  "پیام «خارج از ساعت کاری» بدهد؛ خاموش: شیفت منشی خاموش")
    async def _shift(event, ctx, args):
        s = norm_sec(ctx.acc["sec"])
        a = (args or "").strip()
        if a in ("خاموش", "off", "حذف"):
            s["shift"] = None
            ctx.store.save()
            return await ctx.reply(event, "🕘 شیفت کاری خاموش شد (منشی همیشه جواب می‌دهد)")
        from utils import parse_shift
        p = parse_shift(a)
        if not p:
            return await ctx.reply(event, "❗ فرمت: شیفت منشی 9 تا 18  یا  شیفت منشی 9:30 تا 21:30")
        f, t = p
        s["shift"] = {"from": f, "to": t, "on": True}
        ctx.store.save()
        await ctx.reply(event,
                        f"✅ شیفت کاری: {f // 60:02d}:{f % 60:02d} تا {t // 60:02d}:{t % 60:02d}\n"
                        "بیرون شیفت: پیام «خارج از ساعت کاری» ارسال می‌شود"
                        + ("" if s.get("off_msg") or s["text"] else "\n⚠️ پیام منشی تنظیم نکردی — شیفت فقط وقتی معنا دارد که منشی روشن باشد"))

    # ---------- تایپ جادویی ----------
    @bot.cmd("تایپ جادویی روشن", "typon", cat="منشی",
             help="تایپ جادویی روشن — قبل از جواب خودکار، «در حال تایپ...» نشان داده شود")
    async def _typ_on(event, ctx, args):
        norm_sec(ctx.acc["sec"])["typing"] = True
        ctx.store.save()
        await ctx.reply(event, "⌨️ تایپ جادویی روشن شد (منشی و پاسخ سریع)")

    @bot.cmd("تایپ جادویی خاموش", "typoff", cat="منشی",
             help="تایپ جادویی خاموش — نمایش «در حال تایپ» قطع شود")
    async def _typ_off(event, ctx, args):
        norm_sec(ctx.acc["sec"])["typing"] = False
        ctx.store.save()
        await ctx.reply(event, "⌨️ تایپ جادویی خاموش شد")

    # ---------- تنظیم زمان منشی / تگ ----------
    @bot.cmd("تنظیم زمان منشی", "seccool", cat="منشی",
             help="تنظیم زمان منشی <دقیقه> — فاصله جواب به هر کاربر")
    async def _cool(event, ctx, args):
        try:
            v = max(1, int(args.strip()))
        except ValueError:
            return await ctx.reply(event, "❗ عدد بده: تنظیم زمان منشی 10")
        norm_sec(ctx.acc["sec"])["cool"] = v
        ctx.store.save()
        await ctx.reply(event, f"✅ فاصله جواب منشی: {v} دقیقه")

    @bot.cmd("منشی تگ روشن", "sectagon", cat="منشی",
             help="منشی تگ روشن — توی گروه‌ها هم وقتی منشنت کنند جواب بدهد")
    async def _tagon(event, ctx, args):
        norm_sec(ctx.acc["sec"])["tag"] = True
        ctx.store.save()
        await ctx.reply(event, "🏷 منشی برای منشن‌های گروه هم روشن شد\n"
                                "(فقط وقتی منشنت کنند جواب می‌دهد — نه هر پیام گروه)")

    @bot.cmd("منشی تگ خاموش", "sectagoff", cat="منشی",
             help="منشی تگ خاموش — جواب منشن در گروه‌ها خاموش شود")
    async def _tagoff(event, ctx, args):
        norm_sec(ctx.acc["sec"])["tag"] = False
        ctx.store.save()
        await ctx.reply(event, "🏷 منشی تگ در گروه‌ها خاموش شد")

    # ---------- ارسال پیام منشی (متن یا مدیا) ----------
    async def _send_reply(ctx, uid, reply_to, spec, render=True):
        """spec = off_msg dict؛ متن/مدیا را (با تایپ جادویی) برای uid می‌فرستد."""
        if spec.get("type") == "media":
            chat, mid = spec["chat"], spec["msg"]

            async def _fwd():
                await ctx.client.forward_messages(uid, chat, mid)
            await typing_then(ctx, uid, _fwd)
            return True
        text = spec.get("content") or ""
        if render:
            sender = None
            try:
                sender = await ctx.client.get_entity(uid)
            except Exception:
                pass
            text = render_vars(text, ctx.cfg.tz, user=sender)

        async def _snd():
            kw = {"reply_to": reply_to} if reply_to else {}
            await ctx.client.send_message(uid, text, **kw)
        await typing_then(ctx, uid, _snd)
        return True

    # ---------- لیست سیاه ----------
    async def _add_black(event, ctx, args):
        from utils import get_user
        u = await get_user(ctx.client, event, args)
        if not u:
            return await ctx.reply(event, "❗ کاربر پیدا نشد (ریپلی یا آیدی بده)")
        b = ctx.acc["black"]
        if u.id not in b:
            b.append(u.id)
            ctx.store.save()
        await ctx.reply(event, "⛔ به لیست سیاه اضافه شد")

    async def _del_black(event, ctx, args):
        from utils import get_user
        u = await get_user(ctx.client, event, args)
        if u and u.id in ctx.acc["black"]:
            ctx.acc["black"].remove(u.id)
            ctx.store.save()
        await ctx.reply(event, "✅ از لیست سیاه حذف شد")

    bot.cmd("افزودن سیاه", "blackadd", cat="منشی",
            help="افزودن سیاه <user> — منشی و پاسخ سریع بهش جواب ندهند")(_add_black)
    bot.cmd("حذف سیاه", "blackdel", cat="منشی",
            help="حذف سیاه <user> — خارج کردن از لیست سیاه")(_del_black)
    bot.cmd("لیست سیاه", "blacklist", cat="منشی",
            help="لیست سیاه — نمایش لیست سیاه")(
        lambda event, ctx, args: ctx.reply(
            event, "⛔ لیست سیاه:\n" + "\n".join(f"• <code>{i}</code>" for i in ctx.acc["black"])
            if ctx.acc["black"] else "ℹ️ خالی است"))

    # ---------- هوک اصلی: پیوی + منشن گروه ----------
    @bot.msg_hook
    async def _secretary(event, ctx):
        msg = event.message
        if msg.out:
            return
        if ctx.bot_off(event.chat_id):
            return  # سلف خاموش است — منشی هم جواب ندهد
        s = norm_sec(ctx.acc["sec"])
        private = event.is_private
        if not private:
            # گروه: فقط اگر «منشی تگ روشن» باشد و پیام منشن خودت باشد
            if not s.get("tag"):
                return
            if not getattr(msg, "mentioned", False):
                return
        uid = msg.sender_id
        if not uid or ctx.is_sudo(uid) or uid == 777000:
            return  # 777000 = تلگرام رسمی؛ نباید جواب خودکار بگیرد
        sender = msg.sender
        if not sender or getattr(sender, "bot", False) or isinstance(sender, types.Channel):
            return
        if uid in ctx.acc["black"]:
            return
        # ثبت کاربر دیده‌شده (قبل از ثبت تشخیص بده بار اول است یا نه)
        first_time = str(uid) not in ctx.acc["seen"]
        if first_time:
            ctx.acc["seen"][str(uid)] = int(time.time())
            if len(ctx.acc["seen"]) > 5000:
                oldest = sorted(ctx.acc["seen"].items(), key=lambda x: x[1])[:500]
                for k, _ in oldest:
                    ctx.acc["seen"].pop(k, None)
            ctx.store.save()

        now_ts = time.time()
        idle = now_ts - ctx.last_activity
        if private:
            # ۱) پاسخ افلاین مستقل — اولویت اول: اکانت بی‌فعال + پیام افلاین مسلح
            if s.get("off_on") and s.get("off_msg") and idle >= s["offline_min"] * 60:
                if now_ts - last_reply.get(uid, 0) < s["cool"] * 60:
                    return
                last_reply[uid] = now_ts
                try:
                    await _send_reply(ctx, uid, None, s["off_msg"])
                except Exception:
                    pass
                return
            # ۲) شیفت کاری — بیرون شیفت: پیام «خارج از ساعت کاری»
            sh = s.get("shift")
            if sh and not in_shift(sh, ctx.cfg.tz):
                if now_ts - last_reply.get(uid, 0) < s["cool"] * 60:
                    return
                last_reply[uid] = now_ts
                try:
                    away = s["off_msg"] if s.get("off_msg") else {"type": "text",
                                                                  "content": AWAY_DEFAULT}
                    await _send_reply(ctx, uid, None, away)
                except Exception:
                    pass
                return
        # ۳) منشی معمولی
        if not s["on"] or not s["text"]:
            return
        if s["mode"] == "smart" and not first_time:
            return
        if now_ts - last_reply.get(uid, 0) < s["cool"] * 60:
            return
        last_reply[uid] = now_ts
        try:
            text = render_vars(s["text"], ctx.cfg.tz, user=sender)

            async def _snd():
                if private:
                    await ctx.client.send_message(uid, text)
                else:
                    await event.reply(text)
            await typing_then(ctx, uid, _snd)
        except Exception:
            pass
