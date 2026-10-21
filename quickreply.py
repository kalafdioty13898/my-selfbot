# -*- coding: utf-8 -*-
"""ماژول پاسخ سریع: جواب خودکار متن/استیکر/ویس وقتی کسی کلمه‌ای را گفت."""
import time

from framework import Bot


def setup(bot: Bot):
    cooldown = {}  # user_id -> ts

    @bot.cmd("پاسخ", "qr", cat="پاسخ سریع",
             help="پاسخ 'کلمه' جواب — افزودن پاسخ متنی (یا با ریپلی روی مدیا = جواب مدیا)")
    async def _add(event, ctx, args):
        if not args or not args.strip().startswith("'"):
            return await ctx.reply(event,
                                   "❗ فرمت: پاسخ 'سلام' خوبم تو چطوری؟\n"
                                   "(یا روی استیکر/ویس ریپلی کن و فقط پاسخ 'سلام' بزن)")
        try:
            trigger, rest = args.split("'", 1)[1].split("'", 1)
        except IndexError:
            return await ctx.reply(event, "❗ کوتیشن بسته یادت نره: پاسخ 'کلمه' جواب")
        trigger = trigger.strip()
        if not trigger:
            return await ctx.reply(event, "❗ کلمه خالیه")
        if event.is_reply:
            src = await event.get_reply_message()
            if src and src.media:
                dest = ctx.relay_chat()
                try:
                    fwd = await ctx.client.forward_messages(dest, event.chat_id, src.id)
                except Exception:
                    return await ctx.reply(event, "❌ کپی مدیا ممکن نشد (کانال storage را چک کن)")
                ctx.acc["quick"][trigger.lower()] = {"type": "media", "chat": dest, "msg": fwd.id}
                ctx.store.save()
                return await ctx.reply(event, f"✅ پاسخ مدیایی برای «{trigger}» ثبت شد")
            rest = src.raw_text or ""
        if not (rest or "").strip():
            return await ctx.reply(event, "❗ جواب را بعد از کوتیشن بنویس")
        ctx.acc["quick"][trigger.lower()] = {"type": "text", "content": rest.strip()}
        ctx.store.save()
        await ctx.reply(event, f"✅ پاسخ برای «{trigger}» ثبت شد")

    @bot.cmd("حذف پاسخ", "qrdel", cat="پاسخ سریع",
             help="حذف پاسخ <کلمه> — حذف یک پاسخ سریع")
    async def _del(event, ctx, args):
        t = (args or "").strip().lower()
        if t in ctx.acc["quick"]:
            del ctx.acc["quick"][t]
            ctx.store.save()
            return await ctx.reply(event, "✅ حذف شد")
        await ctx.reply(event, "❗ چنین پاسخی ندارم")

    @bot.cmd("پاسخ ها", "qrs", cat="پاسخ سریع",
             help="پاسخ ها — نمایش همه پاسخ‌های سریع")
    async def _list(event, ctx, args):
        q = ctx.acc["quick"]
        if not q:
            return await ctx.reply(event, "ℹ️ پاسخ سریعی ثبت نشده")
        lines = [f"• «{k}» ← {'مدیا' if v['type'] == 'media' else v['content'][:40]}"
                 for k, v in q.items()]
        await ctx.reply(event, "⚡ پاسخ‌های سریع:\n" + "\n".join(lines))

    @bot.cmd("پاکسازی پاسخ ها", "qrclean", cat="پاسخ سریع",
             help="پاکسازی پاسخ ها — حذف همه پاسخ‌های سریع")
    async def _clean(event, ctx, args):
        ctx.acc["quick"] = {}
        ctx.store.save()
        await ctx.reply(event, "♻️ همه پاسخ‌های سریع پاک شدند")

    # ---------- هوک ----------
    @bot.msg_hook
    async def _qr(event, ctx):
        msg = event.message
        if msg.out:
            return
        text = (msg.raw_text or "").strip().lower()
        if not text:
            return
        uid = msg.sender_id
        if not uid or ctx.is_sudo(uid) or uid in ctx.acc["black"]:
            return
        sender = msg.sender
        if getattr(sender, "bot", False):
            return
        # فقط کلمه اول پیام چک شود (تا وسط جمله‌های عادی نیفتد)
        first = text.split()[0]
        q = ctx.acc["quick"].get(first)
        if not q:
            return
        now_ts = time.time()
        if now_ts - cooldown.get(uid, 0) < 5:
            return
        cooldown[uid] = now_ts
        try:
            if q["type"] == "text":
                from utils import render_vars
                await ctx.client.send_message(event.chat_id,
                                              render_vars(q["content"], ctx.cfg.tz, user=sender),
                                              reply_to=msg.id)
            else:
                await ctx.client.forward_messages(event.chat_id, q["chat"], q["msg"])
        except Exception:
            pass
