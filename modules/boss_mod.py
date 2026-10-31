# -*- coding: utf-8 -*-
"""پنل مدیر فروشگاه — نظارت و بازرسی سرویس سلف مشتری‌ها.

دو لایه:
۱) سرویس: سلامت سشن‌ها، چه دستورهایی به سلفِ خودشان زده‌اند (تله‌متری —
   برای کشف سوءاستفاده مثل بمبر)، ری‌استارت/استاپ/مسدود.
۲) بازرسی (فقط مدیر، فقط خواندنی): «گفتگوهای مشتری» لیست چت‌های اکانتش،
   «بازدید مشتری» خواندن یک چت، «فعالیت مشتری» آخرین پیام‌های خروجی اکانت —
   برای چکِ سوءاستفاده (بمبر/اسپم/کلاهبرداری) طبق توافق قبلی با مشتری.
   هر بازرسی یک خط ردپا در چت لاگ می‌گذارد (چه چیزی، کی — بدون محتوا).

مرز: فرستادن پیام با اکانت مشتری عمداً پیاده نشده — بازرسی یک‌طرفه و
فقط خواندنی است و هیچ دستوری با کلاینت مشتری چیزی نمی‌فرستد.
"""
import html
import time
from zoneinfo import ZoneInfo

from framework import Bot
from telethon.errors import FloodWaitError

TEHRAN = ZoneInfo("Asia/Tehran")
MAX_DYNAMIC = 25  # هماهنگ با bot.py — فقط برای نمایش


def _esc(s):
    return html.escape(str(s or ""))


def _short(s, n=70):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _fmt_time(dt):
    try:
        dt = dt.astimezone(TEHRAN)
        now = time.localtime()
        same_day = (dt.year, dt.month, dt.day) == (now.tm_year, now.tm_mon, now.tm_mday)
        head = "" if same_day else f"{dt.month:02d}/{dt.day:02d} "
        return head + f"{dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return "?"


def _kind_icon(e):
    try:
        cn = type(e).__name__
        if cn == "User":
            return "🤖" if getattr(e, "bot", False) else "👤"
        if cn == "Channel":
            return "📢" if getattr(e, "broadcast", False) else "👥"
        if cn == "Chat":
            return "👥"
    except Exception:
        pass
    return "•"


def _msg_text(msg):
    """متن پیام یا برچسب مدیا (بدون دانلود)."""
    t = (getattr(msg, "raw_text", None) or "").strip()
    if t:
        return t
    if getattr(msg, "action", None) is not None:
        return "⚙️ [سیستمی]"
    if getattr(msg, "media", None) is None:
        return ""
    if getattr(msg, "photo", None):
        return "🖼 [عکس]"
    if getattr(msg, "voice", None):
        return "🎙 [ویس]"
    if getattr(msg, "video_note", None):
        return "⭕️ [ویدیو دایره‌ای]"
    if getattr(msg, "video", None):
        return "🎬 [ویدیو]"
    if getattr(msg, "gif", None):
        return "🎞 [گیف]"
    if getattr(msg, "sticker", None):
        return "🏷 [استیکر]"
    if getattr(msg, "music", None):
        return "🎵 [موسیقی]"
    cn = type(msg.media).__name__
    return {"MessageMediaContact": "👤 [مخاطب]",
            "MessageMediaGeo": "📍 [لوکیشن]",
            "MessageMediaPoll": "📊 [نظرسنجی]",
            "MessageMediaDice": "🎲 [دیس]",
            "MessageMediaGame": "🎮 [بازی]",
            "MessageMediaInvoice": "🧾 [فاکتور]",
            "MessageMediaWebPage": ""}.get(cn, "📎 [فایل]")


async def _sender_name(msg):
    try:
        s = await msg.get_sender()
        if s is None:
            return ""
        return (getattr(s, "first_name", None) or getattr(s, "title", None)
                or getattr(s, "username", None) or "")
    except Exception:
        return "?"


async def _temp_client(ctx, session):
    """کلاینت موقت فقط-خواندنی برای مشتریِ آفلاین (سشن کش‌شده پول).
    در تست‌ها جایگزین می‌شود. None = سشن دیگر معتبر نیست."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    c = TelegramClient(StringSession(session), ctx.cfg.api_id, ctx.cfg.api_hash,
                       device_model="Desktop", system_version="Windows 10",
                       app_version="Star Self 1.0")
    await c.connect()
    if not await c.is_user_authorized():
        try:
            await c.disconnect()
        except Exception:
            pass
        return None
    return c


async def _client_for(ctx, pool, uid):
    """(کلاینت، موقت؟) — آنلاین: کلاینت پول؛ آفلاین: سشن کش‌شده → کلاینت موقت."""
    unit = pool.units.get(uid) if pool else None
    if unit and unit.get("client"):
        return unit["client"], False
    s = (pool.sessions.get(uid) if pool else None)
    if not s:
        return None, False
    try:
        c = await _temp_client(ctx, s)
    except Exception:
        return None, True
    return (c if c else None), True


def _split_uid(args):
    parts = (args or "").split()
    uid = parts[0].lstrip("uU") if parts and parts[0].lstrip("uU").isdigit() else None
    return uid, parts


def setup(bot: Bot):
    def _pool(ctx):
        return getattr(ctx.store, "pool", None)

    def _owner(ctx):
        """اکانت‌های مدیر: کلید عددی (1،2،...) — مشتری‌ها کلیدشان u<uid> است."""
        return not str(ctx.key).startswith("u")

    def _norm_uid(tok):
        tok = (tok or "").strip().lstrip("uU")
        return tok if tok.isdigit() else None

    def _ago(ts):
        if not ts:
            return "—"
        d = int(time.time() - ts)
        if d < 60:
            return f"{d} ثانیه پیش"
        if d < 3600:
            return f"{d // 60} دقیقه پیش"
        if d < 86400:
            return f"{d // 3600} ساعت پیش"
        return f"{d // 86400} روز پیش"

    def _dur(sec):
        sec = int(sec)
        h, m = sec // 3600, (sec % 3600) // 60
        return f"{h} ساعت و {m} دقیقه" if h else f"{m} دقیقه"

    async def _resolve_client(event, ctx, uid):
        """کلاینت مشتری برای بازرسی + پیام خطای مناسب. None = پیام داده‌ایم."""
        pool = _pool(ctx)
        if not pool:
            await ctx.reply(event, "ℹ️ فروشگاه در این ران فعال نیست")
            return None, False, pool
        client, temp = await _client_for(ctx, pool, uid)
        if client is None:
            if temp:
                await ctx.reply(event,
                                f"❗ سشن مشتری <code>{uid}</code> معتبر نیست "
                                "(قطع شده یا بن شده)", parse_mode="html")
            else:
                await ctx.reply(event,
                                f"ℹ️ مشتری <code>{uid}</code> آنلاین نیست و سشنش "
                                "در این ران کش نشده", parse_mode="html")
            return None, False, pool
        return client, temp, pool

    async def _audit(ctx, uid, what):
        """ردپای بازرسی در چت لاگ — بدون محتوا، فقط چه/کی."""
        try:
            await ctx.send(ctx.relay_chat(),
                           f"🔍 بازرسی مشتری <code>{uid}</code> — {what}",
                           parse_mode="html")
        except Exception:
            pass

    @bot.cmd("وضعیت مشتری‌ها", "clients", cat="مدیریت",
             help="وضعیت مشتری‌ها — لیست اکانت‌های فعال خریداران سلف + مدت آنلاین‌بودن")
    async def _clients(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        pool = _pool(ctx)
        if not pool or not pool.units:
            return await ctx.reply(event, "ℹ️ فعلاً مشتری‌ای آنلاین نیست")
        lines = [f"🛒 مشتری‌های آنلاین: {len(pool.units)}/{MAX_DYNAMIC}\n"]
        for uid, u in sorted(pool.units.items()):
            me = u["ctx"].me
            cl = u["ctx"].extra.get("cmdlog")
            last = cl[-1][0] if cl else None
            lines.append(
                f"• <b>{(me.first_name or '?')}</b> — <code>{uid}</code>\n"
                f"  ⏱ آنلاین: {_dur(time.time() - u['since'])} | آخرین دستور: {_ago(last)}")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("مشتری", "client", cat="مدیریت",
             help="مشتری <uid> — جزئیات یک مشتری: وضعیت، آخرین دستورها، بمبر و...")
    async def _client(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid = _norm_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: مشتری 123")
        pool = _pool(ctx)
        if not pool:
            return await ctx.reply(event, "ℹ️ فروشگاه در این ران فعال نیست")
        u = pool.units.get(uid)
        if not u:
            bl = " — 🚫 مسدود شده" if uid in pool.blocked else ""
            return await ctx.reply(event, f"ℹ️ مشتری <code>{uid}</code> آنلاین نیست{bl}",
                                   parse_mode="html")
        c = u["ctx"]
        me = c.me
        lines = [f"🛒 <b>{(me.first_name or '?')}</b>"
                 + (f" {me.last_name or ''}" if getattr(me, "last_name", None) else ""),
                 f"👤 آیدی: <code>{me.id}</code> | کلید: <code>{uid}</code>",
                 f"⏱ آنلاین: {_dur(time.time() - u['since'])}",
                 f"🔐 سشن: کش شده ✅ (ری‌استارت دستی ممکن است)"]
        cl = list(c.extra.get("cmdlog") or [])
        if cl:
            lines.append(f"\n📜 {len(cl)} دستور آخر (جدید → قدیم):")
            for ts, cmd, _cid in reversed(cl[-10:]):
                lines.append(f"  • <code>{cmd}</code> — {_ago(ts)}")
        else:
            lines.append("\n📜 هنوز دستوری به سلفش نزده")
        b = (c.extra.get("bomber") or {})
        if b.get("running"):
            lines.append(f"💣 بمبر فعال است! {b.get('sent', 0)}/{b.get('total', 0)}")
        lines.append(f"\n🔎 بازرسی: «گفتگوهای مشتری <code>{uid}</code>» | "
                     f"«فعالیت مشتری <code>{uid}</code>»")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("لاگ مشتری", "clientlog", cat="مدیریت",
             help="لاگ مشتری <uid> — دستورهایی که به سلفش زده (تله‌متری سرویس؛ خواندن چت‌ها: «گفتگوهای مشتری»)")
    async def _client_log(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid = _norm_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: لاگ مشتری 123")
        pool = _pool(ctx)
        u = pool.units.get(uid) if pool else None
        if not u:
            return await ctx.reply(event, f"ℹ️ مشتری <code>{uid}</code> آنلاین نیست — لاگش هم پاک شده (تا ری‌استارت در حافظه است)",
                                   parse_mode="html")
        cl = list(u["ctx"].extra.get("cmdlog") or [])
        if not cl:
            return await ctx.reply(event, "ℹ️ هنوز دستوری نزده")
        lines = [f"📜 لاگ <code>{uid}</code> — {len(cl)} دستور:"]
        for ts, cmd, _cid in reversed(cl):
            lines.append(f"• <code>{cmd}</code> — {_ago(ts)}")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("ری‌استارت مشتری", "restartclient", cat="مدیریت",
             help="ری‌استارت مشتری <uid> — قطع و وصل دوباره از همان سشن")
    async def _client_restart(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid = _norm_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: ری‌استارت مشتری 123")
        pool = _pool(ctx)
        if not pool:
            return await ctx.reply(event, "ℹ️ فروشگاه در این ران فعال نیست")
        await ctx.reply(event, f"♻️ ری‌استارت <code>{uid}</code>...", parse_mode="html")
        if await pool.restart(uid):
            await ctx.reply(event, f"✅ مشتری <code>{uid}</code> دوباره وصل شد", parse_mode="html")
        else:
            await ctx.reply(event, f"❗ سشنِ <code>{uid}</code> کش نشده — بعد از پول بعدی فروشگاه خودش می‌آید",
                            parse_mode="html")

    @bot.cmd("استاپ مشتری", "stopclient", cat="مدیریت",
             help="استاپ مشتری <uid> — قطع اکانتش + مسدود شدن استارت خودکار تا «اجازه مشتری»")
    async def _client_stop(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid = _norm_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: استاپ مشتری 123")
        pool = _pool(ctx)
        if not pool:
            return await ctx.reply(event, "ℹ️ فروشگاه در این ران فعال نیست")
        pool.blocked.add(uid)
        await pool.stop(uid)
        await ctx.reply(event, f"🛑 مشتری <code>{uid}</code> قطع و مسدود شد — برگشت: «اجازه مشتری {uid}»",
                        parse_mode="html")

    @bot.cmd("اجازه مشتری", "allowclient", cat="مدیریت",
             help="اجازه مشتری <uid> — برداشتن مسدودی + وصل دوباره (اگر سشن کش شده باشد)")
    async def _client_allow(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid = _norm_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: اجازه مشتری 123")
        pool = _pool(ctx)
        if not pool:
            return await ctx.reply(event, "ℹ️ فروشگاه در این ران فعال نیست")
        pool.blocked.discard(uid)
        if uid in pool.sessions:
            ok = await pool.restart(uid)
            await ctx.reply(event,
                            f"✅ مسدودی <code>{uid}</code> برداشته شد"
                            + (" و دوباره وصل شد" if ok else " — وصل‌شدنش با پول بعدی فروشگاه"),
                            parse_mode="html")
        else:
            await ctx.reply(event, f"✅ مسدودی <code>{uid}</code> برداشته شد — با پول بعدی فروشگاه وصل می‌شود",
                            parse_mode="html")

    @bot.cmd("مسدودها", "blockedclients", cat="مدیریت",
             help="مسدودها — لیست مشتری‌هایی که مدیر استاپ کرده")
    async def _blocked(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        pool = _pool(ctx)
        if not pool or not pool.blocked:
            return await ctx.reply(event, "ℹ️ مسدودی‌ای نیست")
        await ctx.reply(event, "🚫 مسدودها: " + "، ".join(f"<code>{u}</code>" for u in sorted(pool.blocked)),
                        parse_mode="html")

    # ---------- بازرسی (فقط خواندنی) ----------

    @bot.cmd("گفتگوهای مشتری", "چت‌های مشتری", "dialogs", cat="مدیریت",
             help="گفتگوهای مشتری <uid> [تعداد] — آخرین چت‌های اکانت مشتری، شماره‌دار برای «بازدید مشتری»")
    async def _client_dialogs(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid, parts = _split_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: گفتگوهای مشتری 123")
        client, temp, pool = await _resolve_client(event, ctx, uid)
        if client is None:
            return
        dlg_list, err = None, None
        try:
            try:
                lim = int(parts[1])
            except (IndexError, ValueError):
                lim = 20
            lim = max(5, min(lim, 40))
            dlg_list = await client.get_dialogs(limit=lim)
        except FloodWaitError as e:
            err = f"⏳ محدودیت تلگرام: {e.seconds} ثانیه صبر کن"
        except Exception as e:
            err = f"❗ خواندن گفتگوها نشد: {e.__class__.__name__}"
        finally:
            if temp:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        if err:
            return await ctx.reply(event, err)
        if not dlg_list:
            return await ctx.reply(event, "ℹ️ گفتگویی پیدا نشد")
        ctx.extra.setdefault("dlgmap", {})[uid] = [
            (d.id, d.name or str(d.id)) for d in dlg_list]
        lines = [f"💬 گفتگوهای مشتری <code>{uid}</code> ({len(dlg_list)} تا آخر):"]
        for i, d in enumerate(dlg_list, 1):
            un = getattr(d, "unread_count", 0) or 0
            extra = f" — 🔴{un}" if un else ""
            lines.append(f"{i}. {_kind_icon(d.entity)} {_esc(d.name) or '—'}{extra}")
        lines.append(f"🔎 خواندن یکی: «بازدید مشتری {uid} <شماره>»")
        await _audit(ctx, uid, "لیست گفتگوها")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("بازدید مشتری", "خواندن چت مشتری", "peek", cat="مدیریت",
             help="بازدید مشتری <uid> <شماره> [تعداد] — پیام‌های آخر یکی از گفتگوهای «گفتگوهای مشتری» (فقط خواندن)")
    async def _client_peek(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid, parts = _split_uid(args)
        if not uid or len(parts) < 2:
            return await ctx.reply(event, "❗ فرمت: بازدید مشتری 123 4 [10]")
        try:
            n = int(parts[1])
            count = int(parts[2]) if len(parts) > 2 else 10
        except ValueError:
            return await ctx.reply(event, "❗ فرمت: بازدید مشتری 123 4 [10]")
        count = max(1, min(count, 30))
        client, temp, pool = await _resolve_client(event, ctx, uid)
        if client is None:
            return
        title, msgs, err = None, [], None
        try:
            dm = ctx.extra.setdefault("dlgmap", {})
            dl = dm.get(uid)
            if not dl:
                dl = [(d.id, d.name or str(d.id))
                      for d in await client.get_dialogs(limit=20)]
                dm[uid] = dl
            if n < 1 or n > len(dl):
                err = f"❗ شماره گفتگو نامعتبر است — اول «گفتگوهای مشتری {uid}»"
            else:
                did, title = dl[n - 1]
                async for m in client.iter_messages(did, limit=count):
                    msgs.append(m)
        except FloodWaitError as e:
            err = f"⏳ محدودیت تلگرام: {e.seconds} ثانیه صبر کن"
        except Exception as e:
            err = f"❗ خواندن پیام‌ها نشد: {e.__class__.__name__}"
        finally:
            if temp:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        if err:
            return await ctx.reply(event, err)
        if not msgs:
            return await ctx.reply(event, "ℹ️ پیامی در این گفتگو پیدا نشد")
        lines = [f"💬 <b>{_esc(title)}</b> — {len(msgs)} پیام آخر (جدید → قدیم):"]
        for i, m in enumerate(msgs, 1):
            name = getattr(m, "post_author", None)
            if not name:
                name = await _sender_name(m)
            if not name:
                name = "—"
            body = _esc(_short(_msg_text(m), 90))
            lines.append(f"{i}. <b>{_esc(name)}</b> "
                         f"<code>{_fmt_time(getattr(m, 'date', None))}</code>: {body or '—'}")
        await _audit(ctx, uid, f"بازدید چت «{_short(title or '', 30)}»")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("فعالیت مشتری", "activity", cat="مدیریت",
             help="فعالیت مشتری <uid> — آخرین پیام خروجیِ اکانت مشتری در هر گفتگو (نمای چک سوءاستفاده)")
    async def _client_activity(event, ctx, args):
        if not _owner(ctx):
            return await ctx.reply(event, "❗ این دستور مال مدیر فروشگاه است")
        uid, _parts = _split_uid(args)
        if not uid:
            return await ctx.reply(event, "❗ فرمت: فعالیت مشتری 123")
        client, temp, pool = await _resolve_client(event, ctx, uid)
        if client is None:
            return
        items, err = [], None
        try:
            for d in await client.get_dialogs(limit=15):
                last = None
                async for m in client.iter_messages(d.id, limit=15, from_user="me"):
                    last = m
                    break
                if last is not None:
                    items.append((last.date, d.name or str(d.id), _msg_text(last)))
            items.sort(key=lambda x: x[0], reverse=True)
        except FloodWaitError as e:
            err = f"⏳ محدودیت تلگرام: {e.seconds} ثانیه صبر کن"
        except Exception as e:
            err = f"❗ خواندن فعالیت نشد: {e.__class__.__name__}"
        finally:
            if temp:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        if err:
            return await ctx.reply(event, err)
        if not items:
            return await ctx.reply(event, "ℹ️ در گفتگوهای اخیرش چیزی نفرستاده")
        lines = [f"📤 آخرین پیام‌های خروجی <code>{uid}</code> (جدید → قدیم):"]
        for dt, tname, body in items[:12]:
            lines.append(f"• <b>{_esc(tname)}</b> <code>{_fmt_time(dt)}</code>: "
                         f"{_esc(_short(body, 80)) or '—'}")
        await _audit(ctx, uid, "فعالیت خروجی")
        await ctx.reply(event, "\n".join(lines), parse_mode="html")
