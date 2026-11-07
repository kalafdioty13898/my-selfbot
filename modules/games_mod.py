# -*- coding: utf-8 -*-
"""ماژول بازی: بازی‌های شانسی تلگرام (تاس/دارت/بسکتبال/فوتبال/بولینگ/اسلات/سکه)
+ بازی گروهی ۲ تا ۱۰ نفره با رتبه‌بندی خودکار
+ مسابقه تاس و نبرد تاس — هم توی گروه هم توی پیوی.

تک‌نفره: «تاس» یا «بسکتبال» → همان لحظه تاس انداخته می‌شود.
گروهی: «بازی بسکتبال» → شروع؛ بقیه با انداختن همان ایموجی وارد می‌شوند؛
بعد از ۱۰ نفر یا ۳ دقیقه، رتبه‌بندی خودکار اعلام می‌شود (توی پیوی هم کار می‌کند).
مسابقه: «شروع بازی تاس برد = 20» → نوبتی تاس می‌ندازید؛ هرکی جمع تاس‌هایش
زودتر به هدف برسد برنده است.
نبرد: «تاس 5» → هرکس ۵ تاس می‌اندازد؛ بیشترین جمع برنده است."""
import html as _html
import random
import re as _re
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
RACE_MAX = 6          # حداکثر بازیکن مسابقه/نبرد
ROUND_SECONDS = 180
RACE_SECONDS = 30 * 60   # سقف مطلق مسابقه
RACE_IDLE = 5 * 60       # اگر ۵ دقیقه کسی تاس نیندازد، مسابقه تمام می‌شود
BATTLE_SECONDS = 180
MEDALS = ["🥇", "🥈", "🥉"]
SEP = "─────────────"


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
        lines.append(f"{MEDALS[i] if i < 3 else '•'} {_html.escape(p['name'])} — {p['val']}")
    if len(order) > 1 and order[0]["val"] != order[-1]["val"]:
        lines.append(f"🎉 برنده: {_html.escape(order[0]['name'])} | بدشانس: {_html.escape(order[-1]['name'])}")
    return "\n".join(lines)


def _pname(name):
    return ((name or "").strip() or "بازیکن")[:24]


def _sender_name(msg):
    s = getattr(msg, "sender", None)
    return _pname(" ".join(x for x in [getattr(s, "first_name", None),
                                       getattr(s, "last_name", None)] if x))


def _expr(vals):
    return " + ".join(str(v) for v in vals) if vals else "—"


def _parse_n(args):
    """«تاس 5» → عدد ۵؛ بدون عدد یا خرابی → None."""
    m = _re.search(r"\d+", args or "")
    if not m:
        return None
    return max(1, min(10, int(m.group())))


def setup(bot: Bot):
    games = {}  # chat_id -> session dict (در حافظه — بازی‌ها کوتاه‌عمرند)

    # ---------- کمکی‌های مشترک مسابقه/نبرد ----------
    def _me_name(ctx):
        return _pname(getattr(ctx.me, "first_name", None) or "شما")

    async def _react_fire(client, chat_id, msg_id):
        try:
            await client(functions.messages.SendReactionRequest(
                peer=chat_id, msg_id=msg_id,
                reaction=[types.ReactionEmoji(emoticon="🔥")]))
        except Exception:
            pass

    async def _edit_board(client, chat_id, g):
        txt = _race_board(g) if g["mode"] == "race" else _battle_board(g)
        try:
            await client.edit_message(chat_id, g["board"], txt, parse_mode="html")
        except Exception:
            try:
                m = await client.send_message(chat_id, txt, parse_mode="html")
                g["board"] = m.id
            except Exception:
                pass

    # ---------- مسابقه تاس ----------
    def _race_add(ctx, g, uid, name):
        g["order"].append(uid)
        g["players"][uid] = {"name": name, "sum": 0, "rolls": []}

    def _race_board(g):
        lines = [f"🎲 <b>مسابقه تاس</b> — هرکی جمعش به <b>{g['target']}</b> رسید برنده‌ست", SEP]
        for i, uid in enumerate(g["order"], 1):
            p = g["players"][uid]
            mark = "👑 " if uid == g.get("owner") else ""
            lines.append(f"{i}. {mark}{_html.escape(p['name'])}: "
                         f"{_expr(p['rolls'])} = <b>{p['sum']}</b>")
        lines.append(SEP)
        if g["order"]:
            nxt = g["players"][g["order"][g["turn"] % len(g["order"])]]["name"]
            lines.append(f"🎯 نوبت: <b>{_html.escape(nxt)}</b> — تاس 🎲 بنداز")
        return "\n".join(lines)

    async def _race_finish(ctx, chat_id, g, timeout=False):
        games.pop(chat_id, None)
        rows = sorted(g["players"].items(), key=lambda kv: -kv[1]["sum"])
        if not rows or (rows[0][1]["sum"] == 0 and rows[0][1]["rolls"] == []):
            return await ctx.send(chat_id, "⏰ مسابقه تاس بدون هیچ تاسی تمام شد")
        if timeout:
            u, p = rows[0]
            return await ctx.send(
                chat_id,
                f"⏰ وقت مسابقه تمام شد! جلوتر: <b>{_html.escape(p['name'])}</b> "
                f"({_expr(p['rolls'])} = {p['sum']})\n"
                "🎮 دوباره: شروع بازی تاس برد = 20",
                parse_mode="html")
        u, p = rows[0]
        await ctx.send(chat_id,
                       f"🏆 <b>{_html.escape(p['name'])}</b> به {g['target']} رسید و برد!\n"
                       f"{_expr(p['rolls'])} = <b>{p['sum']}</b>\n"
                       "🎮 دوباره: شروع بازی تاس برد = 20",
                       parse_mode="html")

    async def _start_race(event, ctx, target):
        if games.get(event.chat_id):
            return await ctx.reply(event, "ℹ️ یک بازی فعال در این چت هست — اول «لغو بازی» بزن")
        g = {"mode": "race", "target": target, "players": {}, "order": [],
             "turn": 0, "owner": ctx.me_id, "warn": 0.0,
             "abs": time.time() + RACE_SECONDS, "idle": time.time() + RACE_IDLE}
        games[event.chat_id] = g
        _race_add(ctx, g, ctx.me_id, _pname(getattr(ctx.me, "first_name", None) or "شما"))
        if event.is_private:
            try:
                peer = await event.get_chat()
                if peer and getattr(peer, "id", None) and peer.id != ctx.me_id:
                    _race_add(ctx, g, peer.id,
                              _pname(getattr(peer, "first_name", None) or "طرف مقابل"))
            except Exception:
                pass
        try:
            board = await ctx.client.send_message(event.chat_id, _race_board(g),
                                                  parse_mode="html")
            g["board"] = board.id
        except Exception:
            games.pop(event.chat_id, None)
            return await ctx.reply(event, "❌ شروع مسابقه ممکن نشد")
        await ctx.reply(event,
                        f"🎲 مسابقه تاس تا <b>{target}</b> شروع شد!\n"
                        "نوبتی تاس 🎲 بندازید — هرکی زودتر جمعش به هدف برسه برنده‌ست\n"
                        "لغو: لغو بازی",
                        parse_mode="html")

    async def _race_dice(event, ctx, g, uid, msg, val):
        chat_id = event.chat_id
        if uid not in g["players"]:
            if not event.is_private and len(g["order"]) >= RACE_MAX:
                return  # ظرفیت گروه پر است
            name = _me_name(ctx) if msg.out else _sender_name(msg)
            _race_add(ctx, g, uid, name)
            await _edit_board(ctx.client, event.chat_id, g)  # تازه‌وارد فوری روی برد بیاد
        cur = g["order"][g["turn"] % len(g["order"])]
        if uid != cur:
            if time.time() - g.get("warn", 0) > 3:
                g["warn"] = time.time()
                nm = g["players"].get(cur, {}).get("name", "…")
                await ctx.send(chat_id,
                               f"⏳ نوبت <b>{_html.escape(nm)}</b> است — تاسِ 🎲 اون بندازه",
                               parse_mode="html")
            return
        p = g["players"][uid]
        p["rolls"].append(val)
        p["sum"] += val
        await _react_fire(ctx.client, chat_id, msg.id)
        if p["sum"] >= g["target"]:
            return await _race_finish(ctx, chat_id, g)
        g["turn"] = (g["turn"] + 1) % len(g["order"])
        g["idle"] = time.time() + RACE_IDLE
        await _edit_board(ctx.client, chat_id, g)

    # ---------- نبرد تاس («تاس 5») ----------
    def _battle_add(ctx, g, uid, name):
        g["order"].append(uid)
        g["players"][uid] = {"name": name, "vals": []}
        return g["players"][uid]

    def _battle_board(g):
        lines = [f"🎲 <b>نبرد تاس</b> — هر نفر <b>{g['n']}</b> تاس", SEP]
        for uid in g["order"]:
            p = g["players"][uid]
            mark = "👑 " if uid == g.get("owner") else ""
            done = "✅" if len(p["vals"]) >= g["n"] else f"({len(p['vals'])}/{g['n']})"
            lines.append(f"{mark}{_html.escape(p['name'])}: {_expr(p['vals'])} {done}")
        lines.append(SEP)
        left = [g["players"][u] for u in g["order"] if len(g["players"][u]["vals"]) < g["n"]]
        if left:
            lines.append("⏳ منتظر: " + "، ".join(_html.escape(p["name"]) for p in left[:4]))
        return "\n".join(lines)

    async def _battle_finish(ctx, chat_id, g, timeout=False):
        games.pop(chat_id, None)
        full = {u: p for u, p in g["players"].items() if len(p["vals"]) >= g["n"]}
        if not full:
            return await ctx.send(chat_id, "ℹ️ نبرد تاس بدون هیچ تاسی تمام شد")
        sums = {u: sum(p["vals"]) for u, p in full.items()}
        top = max(sums.values())
        winners = [u for u, s in sums.items() if s == top]
        if len(winners) > 1 and not timeout:
            # تساوی → تک‌تاس
            g["n"] = 1
            for p in g["players"].values():
                p["vals"] = []
            g["until"] = time.time() + BATTLE_SECONDS
            games[chat_id] = g
            try:
                board = await ctx.client.send_message(chat_id, _battle_board(g),
                                                      parse_mode="html")
                g["board"] = board.id
            except Exception:
                pass
            return await ctx.send(chat_id,
                                  "🤝 مساوی شد! <b>تک‌تاس</b> — هرکس ۱ تاس 🎲 بندازه، "
                                  "بیشتر می‌بره",
                                  parse_mode="html")
        lines = [f"🎲 <b>نبرد تاس</b> — هر نفر {g['n']} تاس" + (" (ناتمام)" if timeout else "")]
        for u in g["order"]:
            if u in full:
                p = full[u]
                mark = "👑 " if u == g.get("owner") else ""
                lines.append(f"{mark}{_html.escape(p['name'])}: "
                             f"{_expr(p['vals'])} = <b>{sums[u]}</b>")
        w = full[winners[0]]
        lines.append(f"🏆 برنده: <b>{_html.escape(w['name'])}</b>"
                     + ("" if len(winners) > 1 or len(sums) < 2
                        else f" (+{top - sorted(sums.values())[-2]})"))
        await ctx.send(chat_id, "\n".join(lines), parse_mode="html")

    async def _start_battle(event, ctx, n):
        if games.get(event.chat_id):
            return await ctx.reply(event, "ℹ️ یک بازی فعال در این چت هست — اول «لغو بازی» بزن")
        g = {"mode": "battle", "n": n, "players": {}, "order": [], "owner": ctx.me_id,
             "until": time.time() + BATTLE_SECONDS}
        games[event.chat_id] = g
        if event.is_private:
            _battle_add(ctx, g, ctx.me_id, _pname(getattr(ctx.me, "first_name", None) or "شما"))
            try:
                peer = await event.get_chat()
                if peer and getattr(peer, "id", None) and peer.id != ctx.me_id:
                    _battle_add(ctx, g, peer.id,
                                _pname(getattr(peer, "first_name", None) or "طرف مقابل"))
            except Exception:
                pass
        try:
            board = await ctx.client.send_message(event.chat_id, _battle_board(g),
                                                  parse_mode="html")
            g["board"] = board.id
        except Exception:
            games.pop(event.chat_id, None)
            return await ctx.reply(event, "❌ شروع نبرد ممکن نشد")
        await ctx.reply(event,
                        f"🎲 نبرد تاس! هرکس <b>{n}</b> تاس 🎲 بندازه — بیشترین جمع می‌بره\n"
                        "لغو: لغو بازی",
                        parse_mode="html")

    async def _battle_dice(event, ctx, g, uid, msg, val):
        p = g["players"].get(uid)
        if p is None:
            if len(g["order"]) >= RACE_MAX:
                return
            p = _battle_add(ctx, g, uid,
                            _me_name(ctx) if msg.out else _sender_name(msg))
        if len(p["vals"]) >= g["n"]:
            return
        p["vals"].append(val)
        await _react_fire(ctx.client, event.chat_id, msg.id)
        if all(len(pp["vals"]) >= g["n"] for pp in g["players"].values()):
            return await _battle_finish(ctx, event.chat_id, g)
        g["until"] = time.time() + BATTLE_SECONDS
        await _edit_board(ctx.client, event.chat_id, g)

    # ================= تک‌نفره =================
    for _fa, _em in GAMES:
        async def _solo(event, ctx, args, _em=_em, _fa=_fa):
            if _em == "🎲":
                n = _parse_n(args)
                if n:
                    return await _start_battle(event, ctx, n)  # «تاس 5»
            try:
                await ctx.client.send_file(event.chat_id, types.InputMediaDice(_em))
            except Exception:
                if _em == "🪙":  # سکه روی همه سرورها نیست — جایگزین محلی
                    r = "🪙 رو" if random.randint(0, 1) else "🦅 خط"
                    return await ctx.reply(event, f"🪙 سکه: {r}")
                return await ctx.reply(event, f"❌ بازی {_fa} الان ممکن نشد")
        bot.cmd(_fa, GAME_EN[_em], cat="بازی",
                help=f"{_fa} — انداختن {_fa} (تک‌نفره)"
                     + ("؛ تاس 5 = نبرد تاس (هرکس ۵ تاس، بیشترین جمع می‌بره)" if _em == "🎲" else "")
                )(_solo)

    # ================= مسابقه تاس — دستور شروع =================
    @bot.cmd("شروع بازی تاس برد", "بازی تاس برد", "تاس برد", "dice race", cat="بازی",
             help="شروع بازی تاس برد = 20 — مسابقه تاس (پیوی/گروه): نوبتی تاس 🎲 بندازید؛ "
                  "هرکی جمع تاس‌هایش زودتر به هدف برسد برنده است. هدف پیش‌فرض 30")
    async def _race_start_cmd(event, ctx, args):
        m = _re.search(r"\d+", args or "")
        target = max(10, min(500, int(m.group()))) if m else 30
        await _start_race(event, ctx, target)

    # ================= راهنما / لغو =================
    @bot.cmd("بازی ها", "games", cat="بازی",
             help="بازی ها — لیست بازی‌ها و راهنمای همه حالت‌ها (پیوی و گروه)")
    async def _games_help(event, ctx, args):
        g = games.get(event.chat_id)
        cur = f"\n🎮 بازی فعال همین چت: {g.get('kind') or g.get('mode')} ({len(g['players'])} نفر)" if g else ""
        await ctx.reply(event,
                        "🎮 تک‌نفره: تاس | دارت | بسکتبال | فوتبال | بولینگ | اسلات | سکه\n"
                        "🎲 مسابقه (پیوی/گروه): «شروع بازی تاس برد = 20» — نوبتی تاس بندازید؛ "
                        "هرکی جمعش زودتر به هدف برسه برنده‌ست\n"
                        "🎲 نبرد تاس (پیوی/گروه): «تاس 5» — هرکس ۵ تاس می‌ندازه، بیشترین جمع می‌بره؛ "
                        "مساوی = تک‌تاس\n"
                        "👥 بازی گروهی (۲ تا ۱۰ نفر): «بازی تاس» یا «بازی بسکتبال»؛ بقیه با انداختن "
                        "همان بازی وارد می‌شوند — توی پیوی هم کار می‌کند (طرفت تاس بندازد وارد میشه)\n"
                        "لغو: لغو بازی" + cur)

    @bot.cmd("لغو بازی", "cancelgame", cat="بازی",
             help="لغو بازی — لغو بازی در حال اجرا (گروهی/مسابقه/نبرد)")
    async def _game_cancel(event, ctx, args):
        g = games.pop(event.chat_id, None)
        await ctx.reply(event, "🛑 بازی لغو شد" if g else "ℹ️ بازی فعالی نیست")

    # ================= بازی گروهی =================
    @bot.cmd("بازی", "game", cat="بازی",
             help="بازی <نوع> — بازی چندنفره ۲ تا ۱۰ نفره؛ مثال: بازی تاس | بازی بسکتبال (پیوی هم می‌شود)")
    async def _game_start(event, ctx, args):
        if not event.is_group and not event.is_private:
            return await ctx.reply(event, "❗ این بازی مال گروه یا پیوی است (تک‌نفره: خود دستور را بزن)")
        em = _kind_emoji(args)
        if not em:
            return await ctx.reply(event, "❗ نوع بازی: " + " | ".join(f"بازی {f}" for f, _ in GAMES))
        kind = next(f for f, e in GAMES if e == em)
        if games.get(event.chat_id):
            g = games[event.chat_id]
            return await ctx.reply(event,
                                   f"ℹ️ یک بازی فعال است ({len(g['players'])} نفر) — "
                                   "همان ایموجی را بنداز یا «لغو بازی» بزن")
        games[event.chat_id] = {"mode": "round", "kind": kind, "emoji": em, "players": {},
                                "maxp": MAX_PLAYERS if event.is_group else 2,
                                "until": time.time() + ROUND_SECONDS}
        try:
            await ctx.client.send_file(event.chat_id, types.InputMediaDice(em))
        except Exception:
            games.pop(event.chat_id, None)
            return await ctx.reply(event, f"❌ شروع بازی {kind} ممکن نشد")
        if event.is_group:
            await ctx.reply(event,
                            f"🎮 بازی {kind} شروع شد!\n"
                            f"هرکس تا {ROUND_SECONDS // 60} دقیقه دیگر {em} بندازد وارد می‌شود "
                            f"(حداکثر {MAX_PLAYERS} نفر) — نتیجه خودکار اعلام می‌شود | لغو: لغو بازی")
        else:
            await ctx.reply(event,
                            f"🎮 بازی {kind} شروع شد!\n"
                            f"تاسِ افتتاحیه‌ی تو ثبت شد — طرفت هم {em} بندازد وارد می‌شود؛ "
                            "نتیجه خودکار اعلام می‌شود | لغو: لغو بازی")

    # ---------- پایان + اعلام نتیجه (بازی گروهی) ----------
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
        if msg.action:
            return
        g = games.get(event.chat_id)
        if not g or g.get("mode", "round") != "round":
            return
        em, val = _dice_emoji(msg)
        if em != g["emoji"] or not val:
            return
        if ctx.bot_off(event.chat_id):
            return
        uid = msg.sender_id or (ctx.me_id if msg.out else None)
        if not uid or uid == 777000:
            return
        if not msg.out and (getattr(msg.sender, "bot", False) or not uid):
            return
        # در گروه تاسِ خودمان (پرتاب افتتاحیه) شمرده نمی‌شود؛ در پیوی شمرده می‌شود
        if msg.out and not event.is_private:
            return
        if time.time() > g["until"] + 5:
            return await _finish(ctx, event.chat_id)
        if uid not in g["players"] and len(g["players"]) >= g["maxp"]:
            return await _finish(ctx, event.chat_id)
        if uid in g["players"]:
            return
        name = (_me_name(ctx) if msg.out else _sender_name(msg))
        g["players"][uid] = {"name": name, "val": val}
        # ثبت با ری‌اکشن 🔥 — اگر ممکن نشد مهم نیست
        await _react_fire(ctx.client, event.chat_id, msg.id)
        if len(g["players"]) >= g["maxp"]:
            await _finish(ctx, event.chat_id)

    # ================= تاسِ مسابقه/نبرد =================
    @bot.msg_hook
    async def _race_battle_dice(event, ctx):
        msg = event.message
        if msg.action:
            return
        g = games.get(event.chat_id)
        if not g or g.get("mode") not in ("race", "battle"):
            return
        em, val = _dice_emoji(msg)
        if em != "🎲" or not val:
            return
        if ctx.bot_off(event.chat_id):
            return
        uid = msg.sender_id or (ctx.me_id if msg.out else None)
        if not uid or uid == 777000:
            return
        if not msg.out and getattr(msg.sender, "bot", False):
            return
        if g["mode"] == "race":
            await _race_dice(event, ctx, g, uid, msg, val)
        else:
            await _battle_dice(event, ctx, g, uid, msg, val)


    @bot.tick_hook
    async def _game_tick(ctx):
        now_ = time.time()
        for chat_id, g in list(games.items()):
            mode = g.get("mode", "round")
            if mode == "round":
                if now_ > g["until"] + 5:  # ۵ ثانیه فرصت برای تاس‌های آخر
                    await _finish(ctx, chat_id)
            elif mode == "race":
                if now_ > min(g["abs"], g["idle"]):
                    await _race_finish(ctx, chat_id, g, timeout=True)
            else:
                if now_ > g["until"]:
                    await _battle_finish(ctx, chat_id, g, timeout=True)

