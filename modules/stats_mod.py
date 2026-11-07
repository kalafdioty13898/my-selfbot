# -*- coding: utf-8 -*-
"""ماژول آمار: «آمار» — آمار پیام‌های تو در همین چت (۷ روز اخیر: تعداد، پرتکرارترین
کلمه‌ها، بیشترین ری‌اکشن‌دهنده) و «آمار کلی» — نمای کلی اکانت (چت‌ها، ناخوانده، بی‌صدا).

همه‌چیز سبک و محدود است تا FloodWait نیفتد: حداکثر ۲۵۰۰ پیام اخیر همین چت،
حداکثر ۱۰۰۰ گفتگو برای نمای کلی."""
import datetime
import html as _html
import time

from framework import Bot

SCAN_LIMIT = 2500
DIALOG_LIMIT = 1000
STOPWORDS = {
    "و", "در", "به", "از", "که", "این", "را", "با", "است", "برای", "من", "تو",
    "او", "هست", "بود", "یک", "تا", "هم", "خوب", "چی", "رو", "کن", "شد", "نه",
    "بله", "ای", "ان", "ها", "می", "ما", "شما", "خیلی", "داره", "کرد", "کنم",
    "the", "and", "to", "of", "in", "is", "it", "for", "on", "my", "me", "you",
}


def _esc(s):
    return _html.escape(str(s or ""))


def _chat_name(event):
    try:
        c = event.chat
        return (getattr(c, "title", None) or
                " ".join(x for x in [getattr(c, "first_name", None),
                                     getattr(c, "last_name", None)] if x) or "این چت")
    except Exception:
        return "این چت"


def _top_words(texts, k=5):
    freq = {}
    for t in texts:
        for w in (t or "").split():
            w = w.strip(".,!؟?،؛:()[]«»\"'…-—|#*_~`")
            if len(w) >= 3 and w.lower() not in STOPWORDS and not w.isdigit():
                key = w.lower()
                freq[key] = freq.get(key, 0) + 1
    return sorted(freq.items(), key=lambda kv: -kv[1])[:k]


def _reaction_people(msgs, k=3):
    """بیشترین ری‌اکشن‌دهنده به پیام‌های من (از recent_reactions)."""
    cnt = {}
    for m in msgs:
        r = getattr(m, "reactions", None)
        for rr in (getattr(r, "recent_reactions", None) or []):
            pid = getattr(rr, "peer_id", None)
            uid = getattr(pid, "user_id", None)
            if uid:
                cnt[uid] = cnt.get(uid, 0) + 1
    return sorted(cnt.items(), key=lambda kv: -kv[1])[:k]


def setup(bot: Bot):
    @bot.cmd("آمار", "stats", cat="عمومی",
             help="آمار [کلی] — آمار پیام‌های تو در همین چت (۷ روز: تعداد، کلمه‌های پرتکرار، "
                  "بیشترین ری‌اکشن‌دهنده)؛ آمار کلی = نمای کلی اکانت")
    async def _stats(event, ctx, args):
        a = (args or "").strip().lower()
        if a in ("کلی", "all", "global", "همه", "اکانت"):
            return await _global_stats(event, ctx)
        note = await ctx.reply(event, "📊 در حال شمارش...")
        try:
            lines = await _chat_stats(event, ctx)
            await ctx.client.edit_message(event.chat_id, note.id, lines, parse_mode="html")
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ نشد: {e}")

    async def _chat_stats(event, ctx):
        t0 = time.time()
        tz = ctx.cfg.tz
        from utils import now as _now
        n = _now(tz)
        today = n.date()
        week_ago = n - datetime.timedelta(days=7)

        mine, mine_today, mine_week = [], 0, 0
        total = 0
        async for m in ctx.client.iter_messages(event.chat_id, limit=SCAN_LIMIT):
            if time.time() - t0 > 45:  # بودجه زمانی
                break
            d = m.date
            if d and d < week_ago:
                break
            total += 1
            if m.out:
                mine.append(m)
                mine_week += 1
                if d:
                    ld = d.astimezone(n.tzinfo)
                    if ld.date() == today:
                        mine_today += 1
        if total == 0:
            return "ℹ️ پیامی برای آمار گرفتن پیدا نشد"
        share = 100.0 * len(mine) / total
        words = _top_words([m.raw_text for m in mine if m.raw_text])
        wtxt = "، ".join(f"{_esc(w)} ({c})" for w, c in words) or "—"
        lines = [
            f"📊 <b>آمار «{_esc(_chat_name(event))}»</b> — ۷ روز اخیر",
            "─────────────",
            f"• پیام کل چت: <b>{total}</b> | پیام تو: <b>{len(mine)}</b> ({share:.0f}٪)",
            f"• امروز: <b>{mine_today}</b> | این هفته: <b>{mine_week}</b>",
        ]
        if words:
            lines.append(f"• پرتکرارترین کلمه‌هات: {wtxt}")
        people = _reaction_people(mine)
        if people:
            names = []
            for uid, c in people:
                try:
                    ent = await ctx.client.get_entity(uid)
                    nm = " ".join(x for x in [getattr(ent, "first_name", None),
                                              getattr(ent, "last_name", None)] if x) or "؟"
                except Exception:
                    nm = str(uid)
                names.append(f"{_esc(nm[:20])} ({c})")
            lines.append("• بیشترین ری‌اکشن به پیام‌هات: " + "، ".join(names))
        return "\n".join(lines)

    async def _global_stats(event, ctx):
        t0 = time.time()
        n_utc = datetime.datetime.now(datetime.timezone.utc)
        groups = channels = users = bots = 0
        unread = muted = 0
        n = 0
        async for d in ctx.client.iter_dialogs(limit=DIALOG_LIMIT):
            if time.time() - t0 > 40:
                break
            n += 1
            unread += getattr(d, "unread_count", 0) or 0
            ent = None
            try:
                ent = d.entity
            except Exception:
                pass
            cn = type(ent).__name__ if ent is not None else ""
            if cn == "User":
                if getattr(ent, "bot", False):
                    bots += 1
                else:
                    users += 1
            elif cn == "Channel":
                if getattr(ent, "broadcast", False):
                    channels += 1
                else:
                    groups += 1
            elif cn == "Chat":
                groups += 1
            ns = getattr(d.dialog, "notify_settings", None)
            mu = getattr(ns, "mute_until", None) if ns else None
            if mu is not None:
                try:
                    if mu > n_utc:
                        muted += 1
                except Exception:
                    pass
        lines = [
            "📊 <b>آمار کلی اکانت</b>",
            "─────────────",
            f"• گفتگوها (تا {DIALOG_LIMIT}): <b>{n}</b>",
            f"• گروه‌ها: <b>{groups}</b> | کانال‌ها: <b>{channels}</b> | "
            f"پیوی: <b>{users}</b> | بات‌ها: <b>{bots}</b>",
            f"• پیام‌های ناخوانده: <b>{unread}</b>",
            f"• چت‌های بی‌صدا: <b>{muted}</b>",
        ]
        await ctx.reply(event, "\n".join(lines), parse_mode="html")
