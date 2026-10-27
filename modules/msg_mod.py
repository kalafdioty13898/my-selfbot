# -*- coding: utf-8 -*-
"""ماژول پیام: پیام زمان‌دار (با زمان‌بندی خودِ تلگرام — حتی اگر سلف خاموش باشد
ارسال می‌شود) + روتر فوروارد خودکار از چت منبع به مقصد با فیلتر نوع محتوا."""
import asyncio
import datetime
import re
import time
import zoneinfo

from telethon.tl import functions, types

from framework import Bot
from utils import marked_id

DUR_RE = re.compile(r"(\d+)\s*(ثانیه|دقیقه|ساعت|روز|هفته)")
HEAD_RE = re.compile(
    r"^((?:\s*\d+\s*(?:ثانیه|دقیقه|ساعت|روز|هفته)\s*(?:و\s*)?)+)(.*)$", re.S)
HM_RE = re.compile(r"^(\d{1,2}):(\d{2})(?:\s+(.*))?$", re.S)

FA_UNITS = {"ثانیه": "ثانیه", "دقیقه": "دقیقه", "ساعت": "ساعت", "روز": "روز", "هفته": "هفته"}

# فیلترهای روتر: فارسی → کد (دو املای ویدیو/ویدئو پشتیبانی می‌شود)
KINDS = {"همه": "all", "متن": "text", "عکس": "photo", "ویدیو": "video", "ویدئو": "video",
         "وویس": "voice", "موزیک": "music", "اهنگ": "music", "آهنگ": "music", "گیف": "gif",
         "استیکر": "sticker", "فایل": "file"}
KIND_FA = {"all": "همه", "text": "متن", "photo": "عکس", "video": "ویدیو", "voice": "وویس",
           "music": "موزیک", "gif": "گیف", "sticker": "استیکر", "file": "فایل"}


def parse_when(arg, tzname="Asia/Tehran"):
    """«3 ساعت و 20 دقیقه سلام» یا «21:30 سلام» → (epoch, human, rest) یا (None, err, None)."""
    arg = (arg or "").strip()
    # ۱) مدت نسبی از اول متن (می‌تواند با «و» چند واحد باشد)
    m = HEAD_RE.match(arg)
    if m and m.group(1).strip():
        units = DUR_RE.findall(m.group(1))
        if units:
            secs = 0
            parts = []
            for n, u in units:
                n = int(n)
                mult = {"ثانیه": 1, "دقیقه": 60, "ساعت": 3600, "روز": 86400, "هفته": 604800}[u]
                if n <= 0 or secs + n * mult > 366 * 86400:
                    return None, "زمان نامعتبر است", None
                secs += n * mult
                parts.append(f"{n} {FA_UNITS[u]}")
            rest = (m.group(2) or "").strip()
            if not rest:
                return None, "متن پیام را بنویس: زمان‌دار 3 ساعت یادت نره", None
            return time.time() + secs, " و ".join(parts) + " بعد", rest
    # ۲) ساعت مشخص 21:30 → امروز؛ اگر گذشته بود فردا
    m = HM_RE.match(arg)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None, "ساعت نامعتبر است", None
        rest = (m.group(3) or "").strip()
        if not rest:
            return None, "متن پیام را بنویس", None
        n = datetime.datetime.now(zoneinfo.ZoneInfo(tzname))
        target = n.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target.timestamp() <= time.time() + 30:
            target += datetime.timedelta(days=1)
        human = target.strftime("%H:%M") + (" امروز" if target.date() == n.date() else " فردا")
        return target.timestamp(), human, rest
    return None, "زمان را نفهمیدم. مثال: زمان‌دار 3 ساعت متن پیام  یا  زمان‌دار 21:30 متن", None


def msg_kind(msg):
    """نوع محتوای پیام برای فیلتر روتر."""
    if getattr(msg, "sticker", None):
        return "sticker"
    if getattr(msg, "gif", None):
        return "gif"
    if getattr(msg, "voice", None):
        return "voice"
    if getattr(msg, "video_note", None):
        return "video"
    if getattr(msg, "video", None):
        return "video"
    if getattr(msg, "audio", None):
        return "music"
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "document", None):
        return "file"
    if getattr(msg, "media", None):
        return "other"
    return "text" if (msg.raw_text or "").strip() else "other"


def kind_match(msg, kinds):
    k = msg_kind(msg)
    if not kinds or "all" in kinds:
        return True
    if k == "other":
        return "all" in kinds  # محتوای شناخته‌نشده فقط با «همه» رد می‌شود
    return k in kinds


def setup(bot: Bot):
    # ================= پیام زمان‌دار =================
    @bot.cmd("زمان‌دار", "sched", cat="پیام",
             help="زمان‌دار 3 ساعت متن — پیام با زمان‌بندی خود تلگرام ارسال می‌شود "
                  "(حتی اگر سلف خاموش باشد!)؛ مدیا: روی آن ریپلی کن؛ ساعت: زمان‌دار 21:30 متن")
    async def _sched(event, ctx, args):
        ts, human, text = parse_when(args, ctx.cfg.tz)
        if ts is None:
            return await ctx.reply(event, f"❗ {human}")
        try:
            if event.is_reply:
                m = await event.get_reply_message()
                if m and m.media:
                    from utils import tmp_path
                    path = await m.download_media(file=tmp_path("sch"))
                    await ctx.client.send_file(event.chat_id, path, caption=m.raw_text or "",
                                               schedule=ts)
                else:
                    await ctx.client.send_message(event.chat_id, m.raw_text or "", schedule=ts)
            else:
                await ctx.client.send_message(event.chat_id, text, schedule=ts)
            await ctx.reply(event,
                            f"⏰ زمان‌دار شد: {human} همین‌جا ارسال می‌شود\n"
                            "لیست: زمان‌دار ها | لغو: لغو زمان‌دار <شماره>")
        except Exception as e:
            await ctx.reply(event, f"❌ نشد: {e.__class__.__name__}")

    @bot.cmd("زمان‌دار ها", "scheds", cat="پیام",
             help="زمان‌دار ها — لیست پیام‌های زمان‌دار همین چت")
    async def _sched_list(event, ctx, args):
        try:
            peer = await ctx.client.get_input_entity(event.chat_id)
            r = await ctx.client(functions.messages.GetScheduledHistoryRequest(peer, hash=0))
            msgs = list(r.messages or [])
            if not msgs:
                return await ctx.reply(event, "ℹ️ پیام زمان‌داری برای این چت نیست")
            lines = []
            for i, m in enumerate(msgs, 1):
                d = m.date.strftime("%m-%d %H:%M") if m.date else "?"
                preview = (m.raw_text or "[مدیا]")[:40].replace("\n", " ")
                lines.append(f"{i}. {d} — {preview}")
            await ctx.reply(event, "⏰ زمان‌دارهای این چت:\n" + "\n".join(lines)
                            + "\nلغو: لغو زمان‌دار <شماره>")
        except Exception as e:
            await ctx.reply(event, f"❌ {e.__class__.__name__}")

    @bot.cmd("لغو زمان‌دار", "schedcancel", cat="پیام",
             help="لغو زمان‌دار <شماره> — حذف یک پیام زمان‌دار (شماره از لیست زمان‌دار ها)")
    async def _sched_cancel(event, ctx, args):
        try:
            i = int((args or "").strip()) - 1
        except ValueError:
            return await ctx.reply(event, "❗ شماره بده (لیست: زمان‌دار ها)")
        try:
            peer = await ctx.client.get_input_entity(event.chat_id)
            r = await ctx.client(functions.messages.GetScheduledHistoryRequest(peer, hash=0))
            msgs = list(r.messages or [])
            if not (0 <= i < len(msgs)):
                return await ctx.reply(event, "❗ چنین شماره‌ای در لیست نیست")
            await ctx.client(functions.messages.DeleteMessagesRequest(peer, [msgs[i].id]))
            await ctx.reply(event, "🗑 پیام زمان‌دار لغو شد")
        except Exception as e:
            await ctx.reply(event, f"❌ {e.__class__.__name__}")

    # ================= روتر فوروارد =================
    async def _resolve(ctx, token, event):
        """«اینجا» = همین چت؛ @یوزرنیم یا آیدی → marked id پایدار."""
        t = (token or "").strip().lstrip("@")
        if t in ("اینجا", "این چت", "اینچت", "."):
            ent = await event.get_chat()
            return marked_id(ent)
        if t.lstrip("-").isdigit():
            ent = await ctx.client.get_entity(int(t))
        else:
            ent = await ctx.client.get_entity("@" + t)
        return marked_id(ent)

    @bot.cmd("روتر جدید", "newrouter", cat="پیام",
             help="روتر جدید <مقصد> (در چت منبع بزن) یا روتر جدید <منبع> به <مقصد> — "
                  "هر پیام منبع خودکار به مقصد فوروارد می‌شود")
    async def _router_add(event, ctx, args):
        a = (args or "").strip()
        if not a:
            return await ctx.reply(event, "❗ مقصد را بده: روتر جدید @کانال_من  یا  روتر جدید @منبع به @مقصد")
        # جداکننده: « به » یا «->» یا «→» یا «>»
        parts = re.split(r"\s+(?:به|->|→|>)\s+", a, maxsplit=1)
        if len(parts) == 2:
            src_tok, dst_tok = parts
        else:
            src_tok, dst_tok = "اینجا", a
        try:
            src = await _resolve(ctx, src_tok, event)
            dst = await _resolve(ctx, dst_tok, event)
        except Exception:
            return await ctx.reply(event, "❌ چت منبع/مقصد پیدا نشد — اول اکانت باید عضو هر دو باشد")
        if src == dst:
            return await ctx.reply(event, "❗ منبع و مقصد یکی است!")
        routers = ctx.acc["routers"]
        for r in routers:
            if r["src"] == src and r["dst"] == dst:
                return await ctx.reply(event, "ℹ️ این روتر قبلاً ساخته شده (لیست: روتر ها)")
        routers.append({"src": src, "dst": dst, "kinds": ["all"],
                        "src_label": src_tok, "dst_label": dst_tok})
        ctx.store.save()
        await ctx.reply(event,
                        f"🧭 روتر {len(routers)} ساخته شد: {src_tok} → {dst_tok}\n"
                        "فیلتر: روتر فیلتر 3 متن عکس | حذف: حذف روتر 3")

    @bot.cmd("روتر فیلتر", "routerfilter", cat="پیام",
             help="روتر فیلتر <شماره> <نوع‌ها> — مثال: روتر فیلتر 1 متن عکس | "
                  "نوع‌ها: همه متن عکس ویدیو وویس موزیک گیف استیکر فایل")
    async def _router_filter(event, ctx, args):
        try:
            tok, kinds_str = args.split(None, 1)
            i = int(tok) - 1
        except (ValueError, AttributeError):
            return await ctx.reply(event, "❗ فرمت: روتر فیلتر 1 متن عکس")
        routers = ctx.acc["routers"]
        if not (0 <= i < len(routers)):
            return await ctx.reply(event, "❗ چنین روتری نیست (لیست: روتر ها)")
        ks = [KINDS[k] for k in kinds_str.split() if k in KINDS]
        if not ks:
            return await ctx.reply(event,
                                   "❗ نوع معتبر نیست: " + " ".join(KINDS.keys()))
        routers[i]["kinds"] = ks
        ctx.store.save()
        fa = "، ".join(KIND_FA.get(k, k) for k in ks)
        await ctx.reply(event, f"✅ فیلتر روتر {i + 1}: {fa}")

    @bot.cmd("روتر ها", "routers", cat="پیام",
             help="روتر ها — لیست روترهای فوروارد خودکار")
    async def _router_list(event, ctx, args):
        routers = ctx.acc["routers"]
        if not routers:
            return await ctx.reply(event, "ℹ️ روتری ساخته نشده — راهنما: روتر جدید @مقصد")
        lines = []
        for i, r in enumerate(routers, 1):
            fa = "، ".join(KIND_FA.get(k, k) for k in r.get("kinds", ["all"]))
            lines.append(f"{i}. {r.get('src_label') or r['src']} → "
                         f"{r.get('dst_label') or r['dst']}  [{fa}]")
        await ctx.reply(event, "🧭 روترها:\n" + "\n".join(lines))

    @bot.cmd("حذف روتر", "delrouter", cat="پیام",
             help="حذف روتر <شماره> — حذف یک روتر")
    async def _router_del(event, ctx, args):
        try:
            i = int((args or "").strip()) - 1
        except ValueError:
            return await ctx.reply(event, "❗ شماره بده (لیست: روتر ها)")
        routers = ctx.acc["routers"]
        if not (0 <= i < len(routers)):
            return await ctx.reply(event, "❗ چنین روتری نیست")
        r = routers.pop(i)
        ctx.store.save()
        await ctx.reply(event, "🗑 روتر حذف شد")

    @bot.msg_hook
    async def _router_fwd(event, ctx):
        msg = event.message
        if msg.out or msg.action:
            return
        routers = ctx.acc.get("routers") or []
        if not routers:
            return
        uid = msg.sender_id
        if uid == 777000 or (uid and uid in ctx.acc["black"]):
            return
        cid = str(event.chat_id)
        for r in routers:
            if str(r.get("src")) != cid:
                continue
            if not kind_match(msg, r.get("kinds", ["all"])):
                continue
            try:
                await msg.forward_to(r.get("dst"))
            except Exception:
                continue

