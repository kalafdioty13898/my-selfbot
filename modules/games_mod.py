# -*- coding: utf-8 -*-
"""ماژول بازی: بازی‌های شانسی تلگرام (تاس/دارت/بسکتبال/فوتبال/بولینگ/اسلات/سکه)
+ بازی گروهی ۲ تا ۱۰ نفره با رتبه‌بندی خودکار.

تک‌نفره: «تاس» یا «بسکتبال» → همان لحظه تاس انداخته می‌شود.
گروهی: «بازی بسکتبال» → شروع؛ بقیه با انداختن همان ایموجی وارد می‌شوند؛
بعد از ۱۰ نفر یا ۳ دقیقه، رتبه‌بندی خودکار اعلام می‌شود."""
import random
import time

from telethon.tl import functions, types

from framework import Bot

GAMES = [  # (فارسی، ایموجی تلگرام)
    ("تاس", "🎲"), ("دارت", "🎯"), ("بسکتبال", "🏀"),
    ("فوتبال", "⚽"), ("بولینگ", "🎳"), ("اسلات", "🎰"), ("سکه", "🪙"),
]
GAME_EN = {"🎲": "dice", "🎯": "darts", "🏀": "basketball",
           "⚽": "football", "🎳": "bowling", "🎰": "slots", "🪙": "coin"}
MAX_PLAYERS = 10
ROUND_SECONDS = 180
MEDALS = ["🥇", "🥈", "🥉"]


def _kind_emoji(name):
    """نام بازی (با پسوند «ها» یا بدون آن) → ایموجی یا None."""
    n = (name or "").strip().replace("\u200c", "").replace(" ", "")
    names = {f.replace("\u200c", "").replace(" ", ""): em for f, em in GAMES}
    if n.endswith("ها"):
        n = n[:-2]
    return names.get(n)


def _dice_emoji(msg):
    """ایموجی و عدد تاس پیام (اگر پیام تاس باشد)؛ وگرنه (None, None)."""
    m = getattr(msg, "media", None)
    em = getattr(m, "emoticon", None)
    if em is None:
        return None, None
    val = getattr(m, "value", 0) or 0
    return em, int(val)


def _rank_text(kind, players):
    order = sorted(players.values(), key=lambda p: -p["val"])
    lines = [f"🏆 نتیجه بازی <b>{kind}</b> ({len(order)} نفر):"]
    for i, p in enumerate(order):
        lines.append(f"{MEDALS[i] if i < 3 else '•'} {p['name']} — {p['val']}")
    if len(order) > 1 and order[0]["val"] != order[-1]["val"]:
        lines.append(f"🎉 برنده: {order[0]['name']} | بدشانس: {order[-1]['name']}")
    return "\n".join(lines)


def setup(bot: Bot):
    games = {}  # chat_id -> session dict (در حافظه — بازی‌ها کوتاه‌عمرند)

    # ================= تک‌نفره =================
    for _fa, _em in GAMES:
        async def _solo(event, ctx, args, _em=_em, _fa=_fa):
            try:
                await ctx.client.send_file(event.chat_id, types.InputMediaDice(_em))
            except Exception:
                if _em == "🪙":  # سکه روی همه سرورها نیست — جایگزین محلی
                    r = "🪙 رو" if random.randint(0, 1) else "🦅 خط"
                    return await ctx.reply(event, f"🪙 سکه: {r}")
                return await ctx.reply(event, f"❌ بازی {_fa} الان ممکن نشد")
        bot.cmd(_fa, GAME_EN[_em], cat="بازی",
                help=f"{_fa} — انداختن {_fa} (تک‌نفره)")(_solo)

    # ================= گروهی =================
    @bot.cmd("بازی ها", "games", cat="بازی",
             help="بازی ها — لیست بازی‌ها و راهنمای بازی گروهی")
    async def _games_help(event, ctx, args):
        g = games.get(event.chat_id)
        cur = f"\n🎮 بازی فعال همین چت: {g['kind']} ({len(g['players'])} نفر)" if g else ""
        await ctx.reply(event,
                        "🎮 تک‌نفره: تاس | دارت | بسکتبال | فوتبال | بولینگ | اسلات | سکه\n"
                        "👥 گروهی (۲ تا ۱۰ نفر): «بازی تاس» یا «بازی بسکتبال» را در گروه بزن؛\n"
                        "بقیه با انداختن همان بازی تا ۳ دقیقه وارد می‌شوند و نتیجه خودکار اعلام می‌شود.\n"
                        "لغو: لغو بازی" + cur)

    @bot.cmd("لغو بازی", "cancelgame", cat="بازی",
             help="لغو بازی — لغو بازی گروهی در حال اجرا")
    async def _game_cancel(event, ctx, args):
        g = games.pop(event.chat_id, None)
        await ctx.reply(event, "🛑 بازی لغو شد" if g else "ℹ️ بازی فعالی نیست")

    @bot.cmd("بازی", "game", cat="بازی",
             help="بازی <نوع> — بازی گروهی ۲ تا ۱۰ نفره؛ مثال: بازی تاس | بازی بسکتبال")
    async def _game_start(event, ctx, args):
        if not event.is_group:
            return await ctx.reply(event, "❗ بازی گروهی مال گروه است (تک‌نفره: خود دستور را بزن)")
        em = _kind_emoji(args)
        if not em:
            return await ctx.reply(event, "❗ نوع بازی: " + " | ".join(f"بازی {f}" for f, _ in GAMES))
        kind = next(f for f, e in GAMES if e == em)
        if games.get(event.chat_id):
            g = games[event.chat_id]
            return await ctx.reply(event,
                                   f"ℹ️ یک بازی {g['kind']} فعال است ({len(g['players'])} نفر) — "
                                   "همان ایموجی را بنداز یا «لغو بازی» بزن")
        games[event.chat_id] = {"kind": kind, "emoji": em, "players": {},
                                "until": time.time() + ROUND_SECONDS}
        try:
            await ctx.client.send_file(event.chat_id, types.InputMediaDice(em))
        except Exception:
            games.pop(event.chat_id, None)
            return await ctx.reply(event, f"❌ شروع بازی {kind} ممکن نشد")
        await ctx.reply(event,
                        f"🎮 بازی {kind} شروع شد!\n"
                        f"هرکس تا {ROUND_SECONDS // 60} دقیقه دیگر {em} بندازد وارد می‌شود "
                        f"(حداکثر {MAX_PLAYERS} نفر) — نتیجه خودکار اعلام می‌شود | لغو: لغو بازی")

    # ---------- پایان + اعلام نتیجه ----------
    async def _finish(ctx, chat_id):
        g = games.pop(chat_id, None)
        if not g:
            return
        try:
            await ctx.client.send_message(chat_id, _rank_text(g["kind"], g["players"]),
                                          parse_mode="html")
        except Exception:
            pass

    @bot.msg_hook
    async def _game_join(event, ctx):
        msg = event.message
        if msg.out or msg.action:
            return
        g = games.get(event.chat_id)
        if not g:
            return
        em, val = _dice_emoji(msg)
        if em != g["emoji"] or not val:
            return
        uid = msg.sender_id
        if not uid or getattr(msg.sender, "bot", False) or uid == 777000:
            return
        if time.time() > g["until"] + 5:
            return await _finish(ctx, event.chat_id)
        if uid not in g["players"] and len(g["players"]) >= MAX_PLAYERS:
            return await _finish(ctx, event.chat_id)
        if uid in g["players"]:
            return
        name = " ".join(x for x in [getattr(msg.sender, "first_name", None),
                                    getattr(msg.sender, "last_name", None)] if x) or "بازیکن"
        g["players"][uid] = {"name": name[:24], "val": val}
        # ثبت با ری‌اکشن 🔥 — اگر ممکن نشد مهم نیست
        try:
            await ctx.client(functions.messages.SendReactionRequest(
                peer=event.chat_id, msg_id=msg.id,
                reaction=[types.ReactionEmoji(emoticon="🔥")]))
        except Exception:
            pass
        if len(g["players"]) >= MAX_PLAYERS:
            await _finish(ctx, event.chat_id)

    @bot.tick_hook
    async def _game_tick(ctx):
        for chat_id, g in list(games.items()):
            if time.time() > g["until"] + 5:  # ۵ ثانیه فرصت برای تاس‌های آخر
                await _finish(ctx, chat_id)
