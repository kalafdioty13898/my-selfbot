# -*- coding: utf-8 -*-
"""پنل مدیر فروشگاه — نظارت روی «سرویس» سلف مشتری‌ها (نه چت‌هایشان)

چیزی که این پنل می‌دهد: سلامت سشن‌ها، چه دستورهایی به سلفِ خودشان زده‌اند
(تله‌متری نرم‌افزار — برای کشف سوءاستفاده مثل بمبر)، ری‌استارت/استاپ/مسدود.

مرز اخلاقی/قانونی: وارد چت‌های خصوصی مشتری شدن یا با اکانتش پیام فرستادن
جاسوسی است و عمداً در این ماژول جایی ندارد.
"""
import time

from framework import Bot

MAX_DYNAMIC = 25  # هماهنگ با bot.py — فقط برای نمایش


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
        await ctx.reply(event, "\n".join(lines), parse_mode="html")

    @bot.cmd("لاگ مشتری", "clientlog", cat="مدیریت",
             help="لاگ مشتری <uid> — دستورهایی که به سلفش زده (تله‌متری؛ چت‌هایش دیده نمی‌شود)")
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
