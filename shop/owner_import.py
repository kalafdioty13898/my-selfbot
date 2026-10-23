# -*- coding: utf-8 -*-
"""افزودن اکانت‌های خودت از طریق گیت‌هاب — بدون خرید، بدون کد، بدون QR.

یک Secret با نام OWNER_SESSIONS در گیت‌هاب بساز (هر خط = یک StringSession
~۳۶۰ حرفی). هر بار ربات فروش بالا بیاید این ماژول همگام می‌کند:

  ➕ سشن جدید در Secret     →  هویت واقعی (user_id) با اتصال کوتاه Telethon
                              گرفته می‌شود، ردیف پلن «owner» (۱۰ سال) ثبت و
                              دیتابیس فوراً push می‌شود.
  🔁 سشن همان اکانت عوض شود →  ردیف قبلی لغو، سشن جدید جای آن می‌نشیند
                              (کلاینت قبلی در سلف‌بات قطع و جدید استارت می‌شود).
  ⛔ سشن از Secret حذف شود  →  فعال‌سازی‌اش لغو و سلفش در سلف‌بات قطع می‌شود.

یعنی مدیریت اکانت‌های خودت = ویرایش یک Secret + Run workflow.
سلف‌بات هم از مسیر معمول ShopSync (فچ گیت هر ۶۰ ثانیه) آن‌ها را زنده اجرا می‌کند.
"""
import asyncio
import hashlib
import logging

log = logging.getLogger("star_self.owner")

OWNER_PLAN = "owner"
OWNER_DAYS = 3650          # ۱۰ سال — عملاً بدون انقضا
RESOLVE_TIMEOUT = 90       # سقف گرفتن هویت هر سشن (ثانیه)


def fp_of(session: str) -> str:
    """اثر انگشت سشن برای مقایسه بدون ذخیره‌ی خام."""
    return hashlib.sha1((session or "").encode()).hexdigest()[:16]


def parse_sessions(raw: str) -> list:
    """OWNER_SESSIONS را به فهرست سشن تمیز تبدیل می‌کند.

    جداکننده: خط جدید، ویرگول، سمی‌کالن. تکراری‌ها حذف، خراب‌ها (کوتاه یا
    دارای فاصله داخلی) رد می‌شوند — همان قاعده «سلف دستی» ادمین.
    """
    out, seen = [], set()
    for chunk in str(raw or "").replace("\r", "\n").replace(";", ",").split("\n"):
        for part in chunk.split(","):
            s = part.strip()
            if not s or s in seen:
                continue
            if len(s) < 200 or len(s.split()) > 1:
                log.warning("OWNER_SESSIONS: یک خط نامعتبر رد شد (طول=%d)", len(s))
                continue
            seen.add(s)
            out.append(s)
    return out


async def resolve_identity(cfg, session: str) -> dict:
    """اتصال کوتاه Telethon برای گرفتن user_id واقعی صاحب سشن."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from handlers.activate import DEVICE

    client = TelegramClient(StringSession(session), cfg.api_id, cfg.api_hash, **DEVICE)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("سشن معتبر نیست یا منقضی شده (not authorized)")
        me = await client.get_me()
        return {
            "uid": int(me.id),
            "username": me.username or "",
            "first_name": me.first_name or "",
            "phone": me.phone or "",
        }
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def import_owner_sessions(db, cfg, resolver=None) -> dict:
    """همگام‌سازی Secret با جدول activations. خروجی: خلاصه‌ی تغییرات."""
    resolver = resolver or resolve_identity
    want_list = parse_sessions(cfg.owner_sessions_raw)
    want = {fp_of(s): s for s in want_list}

    summary = {"added": [], "updated": 0, "revoked": 0, "unchanged": 0,
               "errors": []}

    cur = await db.conn.execute(
        "SELECT * FROM activations WHERE plan=?", (OWNER_PLAN,))
    owner_rows = await cur.fetchall()

    by_fp, keep_uid, handled = {}, {}, set()
    for row in owner_rows:
        raw_s = (row["session_enc"] or "")
        from crypto import dec
        s = dec(raw_s)
        f = fp_of(s) if s else ""
        by_fp[f] = row

    # ۱) ردیف‌های موجود: نگه‌داشتن / لغو
    for row in owner_rows:
        from crypto import dec
        s = dec(row["session_enc"] or "")
        f = fp_of(s) if s else ""
        if f in want:
            from utils import parse_dt, naive_now
            exp = parse_dt(row["expires_at"])
            soon = (not exp) or ((exp - naive_now()).days < 90)
            if row["status"] != "active" or soon:
                from utils import now, FMT
                from datetime import timedelta
                new_exp = (now() + timedelta(days=OWNER_DAYS)).strftime(FMT)
                await db.conn.execute(
                    "UPDATE activations SET status='active', expires_at=?, warned=0 "
                    "WHERE id=?", (new_exp, row["id"]))
                await db.conn.commit()
                summary["updated"] += 1
            else:
                summary["unchanged"] += 1
            keep_uid[row["user_id"]] = row["id"]
            handled.add(row["id"])
        else:
            if row["status"] == "active":
                await db.conn.execute(
                    "UPDATE activations SET status='revoked' WHERE id=?", (row["id"],))
                await db.conn.commit()
                summary["revoked"] += 1
                log.info("OWNER_SESSIONS: سشن uid=%s از Secret حذف شده — لغو شد",
                         row["user_id"])

    # ۲) سشن‌های جدید (آن‌هایی که هنوز ردیف owner ندارند — شبکه لازم دارند)
    for f, session in want.items():
        if f in by_fp and by_fp[f]["id"] in handled:
            continue  # در مرحله ۱ همین را فعال نگه داشتیم
        try:
            ident = await asyncio.wait_for(
                resolver(cfg, session), timeout=RESOLVE_TIMEOUT)
            uid = ident["uid"]
            await db.ensure_user(uid, ident["username"], ident["first_name"])

            # یک اکانت = فقط یک سلف فعال؛ بقیه ردیف‌های فعال همان uid لغو شوند
            cur2 = await db.conn.execute(
                "SELECT id FROM activations WHERE user_id=? AND status='active'",
                (uid,))
            for r2 in await cur2.fetchall():
                if r2["id"] == keep_uid.get(uid):
                    continue
                await db.conn.execute(
                    "UPDATE activations SET status='revoked' WHERE id=?",
                    (r2["id"],))
                await db.conn.commit()
                summary["updated"] += 1

            from crypto import enc
            aid = await db.add_activation(
                uid, enc(session),
                enc(ident["phone"]) if ident.get("phone") else "",
                OWNER_PLAN, OWNER_DAYS, "")
            keep_uid[uid] = aid
            summary["added"].append(
                f"{ident.get('first_name') or 'اکانت'} (🆔 {uid})")
            log.info("OWNER_SESSIONS: اکانت uid=%s اضافه شد (aid=%s)", uid, aid)
            # خبر فعال‌سازی به خود اکانت
            try:
                from utils import now as _now
                from datetime import timedelta as _td
                exp = (_now() + _td(days=OWNER_DAYS)).strftime("%Y-%m-%d %H:%M")
                await cfg.bot.send_message(
                    uid, "✅ سلف این اکانت از طریق گیت‌هاب (OWNER_SESSIONS) فعال شد؛ "
                         f"اعتبار تا {exp}")
            except Exception:
                pass
        except asyncio.TimeoutError:
            summary["errors"].append(f"سشن {f[:8]}…: زمان گرفتن هویت تمام شد")
        except Exception as e:
            summary["errors"].append(f"سشن {f[:8]}…: {e}")

    return summary


async def run_owner_import(db, cfg):
    """نقطه ورود bot.py — ایمن، با پوش فوری و گزارش به ادمین."""
    try:
        s = await import_owner_sessions(db, cfg)
    except Exception:
        log.exception("owner import failed")
        return
    changed = s["added"] or s["updated"] or s["revoked"] or s["errors"]
    log.info("OWNER_SESSIONS: +%(a)d اضافه / %(u)d به‌روز / %(r)d لغو / %(n)d بدون تغییر",
             {"a": len(s["added"]), "u": s["updated"], "r": s["revoked"],
              "n": s["unchanged"]})
    if not changed:
        return

    # پوش فوری دیتابیس + بیدارکردن سلف‌بات تا سلف‌های جدید همان لحظه بالا بیایند
    try:
        from git_sync import push_db_snapshot
        from handlers.common import maybe_dispatch
        await push_db_snapshot(db)
        await maybe_dispatch(cfg)
    except Exception:
        log.exception("owner import push failed")

    lines = ["⚙️ همگام‌سازی اکانت‌های گیت‌هاب (OWNER_SESSIONS)"]
    if s["added"]:
        lines.append("➕ اضافه شد: " + "؛ ".join(s["added"]))
    if s["updated"]:
        lines.append(f"🔁 به‌روز/جابه‌جا شد: {s['updated']}")
    if s["revoked"]:
        lines.append(f"⛔ لغو شد: {s['revoked']}")
    if s["errors"]:
        lines.append("⚠️ خطاها:\n" + "\n".join(f"• {e}" for e in s["errors"]))

    bot = getattr(cfg, "bot", None)
    if bot and cfg.admin_id:
        try:
            await bot.send_message(cfg.admin_id, "\n".join(lines))
        except Exception:
            log.warning("owner import report send failed")
