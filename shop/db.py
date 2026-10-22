# -*- coding: utf-8 -*-
"""پایگاه‌داده SQLite ربات فروش star self (aiosqlite).

جدول‌ها:
  users         → کاربران + موجودی سکه
  activations   → سلف‌های فعال/منقضی/لغوشده (سشن رمزنگاری‌شده)
  transactions  → تراکنش‌های سکه
  receipts      → رسیدهای کارت‌به‌کارت
  settings      → تنظیمات قابل ویرایش از پنل ادمین
"""
import json
import os
from datetime import datetime, timedelta

import aiosqlite

from utils import now, FMT, parse_dt as utils_parse, naive_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY,
  username TEXT DEFAULT '',
  first_name TEXT DEFAULT '',
  balance INTEGER DEFAULT 0,
  referred_by INTEGER,
  banned INTEGER DEFAULT 0,
  joined_at TEXT
);
CREATE TABLE IF NOT EXISTS activations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  session_enc TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  plan TEXT DEFAULT 'coin_1d',
  expires_at TEXT,
  status TEXT DEFAULT 'active',
  note TEXT DEFAULT '',
  warned INTEGER DEFAULT 0,
  last_ping TEXT DEFAULT '',
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  type TEXT,
  amount INTEGER,
  meta TEXT DEFAULT '',
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS receipts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  coins INTEGER,
  toman INTEGER,
  file_id TEXT,
  file_type TEXT,
  status TEXT DEFAULT 'pending',
  created_at TEXT,
  decided_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {
    "coin_price": "1000",        # تومان به ازای هر سکه
    "min_buy": "30",             # حداقل خرید سکه
    "activation_cost": "15",     # هزینه فعال‌سازی (سکه)
    "initial_days": "1",         # اعتبار اولیه بعد از فعال‌سازی
    "daily_renew": "3",          # تمدید خودکار روزانه (سکه)
    "card_number": "5022291608588057",
    "card_owner": "فاطمه ابارشی",
    "plan_2m_price": "150000",   # تومان
    "plan_4m_price": "250000",   # تومان
    "min_transfer": "20",
    "max_transfer": "10000",
    "daily_cap": "5000",
    "ref_reward": "3",           # پاداش دعوت‌کننده
    "ref_gift": "2",             # هدیه دعوت‌شده
    "admin_note": "سلف خریداری شده از @st4r_self_bot",
    "force_on": "0",
    "force_channels": "[]",
}


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    # ---------- lifecycle ----------
    async def init(self, admin_id: int = 0):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        for k, v in DEFAULTS.items():
            await self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, str(v)))
        if admin_id:
            # کیف پول ادمین: ۱,۰۰۰,۰۰۰ سکه اولیه
            await self.conn.execute(
                "INSERT OR IGNORE INTO users(user_id, username, first_name, balance, joined_at) "
                "VALUES(?, '', 'ادمین', 1000000, ?)",
                (admin_id, now().strftime(FMT)))
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ---------- settings ----------
    async def sget(self, key, default=""):
        cur = await self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default

    async def sset(self, key, value):
        await self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        await self.conn.commit()

    async def sint(self, key, default=0):
        try:
            return int((await self.sget(key)).strip())
        except (ValueError, TypeError):
            return default

    async def channels(self):
        try:
            return json.loads(await self.sget("force_channels", "[]"))
        except (ValueError, TypeError):
            return []

    async def set_channels(self, lst):
        await self.sset("force_channels", json.dumps(lst, ensure_ascii=False))

    async def force_on(self) -> bool:
        return (await self.sget("force_on", "0")) == "1"

    # ---------- users ----------
    async def user(self, uid: int):
        cur = await self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        return await cur.fetchone()

    async def user_by_username(self, un: str):
        un = (un or "").strip().lstrip("@").lower()
        if not un:
            return None
        cur = await self.conn.execute("SELECT * FROM users WHERE lower(username)=?", (un,))
        return await cur.fetchone()

    async def ensure_user(self, uid: int, username: str, first_name: str, ref: int | None = None):
        """ثبت/به‌روزرسانی کاربر. اگر جدید بود و دعوت معتبر داشت، پاداش‌ها پرداخت می‌شود."""
        row = await self.user(uid)
        if row is not None:
            await self.conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username or row["username"], first_name or row["first_name"], uid))
            await self.conn.commit()
            return {"created": False, "credited": False}

        ref = int(ref) if ref else None
        if ref == uid:
            ref = None
        referrer_ok = bool(ref) and (await self.user(ref)) is not None

        await self.conn.execute(
            "INSERT INTO users(user_id, username, first_name, referred_by, joined_at) "
            "VALUES(?,?,?,?,?)",
            (uid, username or "", first_name or "",
             ref if referrer_ok else None, now().strftime(FMT)))

        credited = False
        if referrer_ok:
            reward = await self.sint("ref_reward", 3)
            gift = await self.sint("ref_gift", 2)
            if reward:
                await self.add_balance(ref, reward, "referral", f"دعوت کاربر {uid}", commit=False)
            if gift:
                await self.add_balance(uid, gift, "gift", "هدیه ثبت‌نام با دعوت", commit=False)
            credited = True
        await self.conn.commit()
        return {"created": True, "credited": credited}

    async def balance(self, uid: int) -> int:
        cur = await self.conn.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        return row["balance"] if row else 0

    async def add_balance(self, uid: int, delta: int, ttype: str, meta: str = "", commit: bool = True):
        """تغییر موجودی + ثبت تراکنش. کسر تا صفر clamp می‌شود."""
        if delta < 0:
            await self.conn.execute(
                "UPDATE users SET balance = MAX(0, balance + ?) WHERE user_id=?", (delta, uid))
        else:
            await self.conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, uid))
        await self.conn.execute(
            "INSERT INTO transactions(user_id, type, amount, meta, created_at) VALUES(?,?,?,?,?)",
            (uid, ttype, delta, meta, now().strftime(FMT)))
        if commit:
            await self.conn.commit()
        return await self.balance(uid)

    async def set_ban(self, uid: int, banned: int):
        await self.conn.execute("UPDATE users SET banned=? WHERE user_id=?", (banned, uid))
        await self.conn.commit()

    async def transfer(self, src: int, dst: int, amount: int):
        """انتقال اتمیک سکه (یک commit)."""
        await self.add_balance(src, -amount, "transfer_out", f"به {dst}", commit=False)
        await self.add_balance(dst, amount, "transfer_in", f"از {src}", commit=False)
        await self.conn.commit()

    async def today_transfer_sum(self, uid: int) -> int:
        today = now().strftime("%Y-%m-%d")
        cur = await self.conn.execute(
            "SELECT -COALESCE(SUM(amount),0) s FROM transactions "
            "WHERE user_id=? AND type='transfer_out' AND substr(created_at,1,10)=?",
            (uid, today))
        row = await cur.fetchone()
        return int(row["s"] or 0)

    async def last_transactions(self, uid: int, n: int = 10):
        cur = await self.conn.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, n))
        return await cur.fetchall()

    async def ref_count(self, uid: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) c FROM users WHERE referred_by=?", (uid,))
        return (await cur.fetchone())["c"]

    async def ref_earned(self, uid: int) -> int:
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM transactions "
            "WHERE user_id=? AND type='referral'", (uid,))
        return int((await cur.fetchone())["s"] or 0)

    async def all_users(self):
        cur = await self.conn.execute("SELECT user_id FROM users")
        return await cur.fetchall()

    # ---------- receipts ----------
    async def add_receipt(self, uid, coins, toman, file_id, ftype) -> int:
        cur = await self.conn.execute(
            "INSERT INTO receipts(user_id, coins, toman, file_id, file_type, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (uid, coins, toman, file_id, ftype, now().strftime(FMT)))
        await self.conn.commit()
        return cur.lastrowid

    async def pending_receipt_of(self, uid: int):
        cur = await self.conn.execute(
            "SELECT * FROM receipts WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (uid,))
        return await cur.fetchone()

    async def pending_receipts(self):
        cur = await self.conn.execute(
            "SELECT * FROM receipts WHERE status='pending' ORDER BY id")
        return await cur.fetchall()

    async def receipt(self, rid: int):
        cur = await self.conn.execute("SELECT * FROM receipts WHERE id=?", (rid,))
        return await cur.fetchone()

    async def decide_receipt(self, rid: int, status: str):
        await self.conn.execute(
            "UPDATE receipts SET status=?, decided_at=? WHERE id=?",
            (status, now().strftime(FMT), rid))
        await self.conn.commit()

    # ---------- activations ----------
    async def add_activation(self, uid, session_enc, phone, plan, days, note="") -> int:
        expires = (now() + timedelta(days=days)).strftime(FMT)
        cur = await self.conn.execute(
            "INSERT INTO activations(user_id, session_enc, phone, plan, expires_at, note, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (uid, session_enc, phone, plan, expires, note, now().strftime(FMT)))
        await self.conn.commit()
        return cur.lastrowid

    async def active_of(self, uid: int):
        cur = await self.conn.execute(
            "SELECT * FROM activations WHERE user_id=? AND status='active' "
            "ORDER BY id DESC LIMIT 1", (uid,))
        return await cur.fetchone()

    async def all_active(self):
        cur = await self.conn.execute(
            "SELECT * FROM activations WHERE status='active' ORDER BY id")
        return await cur.fetchall()

    async def all_activations(self):
        cur = await self.conn.execute("SELECT * FROM activations ORDER BY id DESC")
        return await cur.fetchall()

    async def extend(self, uid: int, days: int):
        """تمدید از حداکثر(الان، پایان فعلی)."""
        act = await self.active_of(uid)
        if not act:
            return None
        base = utils_parse(act["expires_at"]) or naive_now()
        if base < naive_now():
            base = naive_now()
        new_exp = (base + timedelta(days=days)).strftime(FMT)
        await self.conn.execute(
            "UPDATE activations SET expires_at=?, warned=0 WHERE id=?", (new_exp, act["id"]))
        await self.conn.commit()
        return new_exp

    async def expire_due(self) -> int:
        t = now().strftime(FMT)
        cur = await self.conn.execute(
            "UPDATE activations SET status='expired' WHERE status='active' AND expires_at <= ?", (t,))
        await self.conn.commit()
        return cur.rowcount or 0

    async def revoke(self, aid: int):
        cur = await self.conn.execute("SELECT * FROM activations WHERE id=?", (aid,))
        row = await cur.fetchone()
        await self.conn.execute(
            "UPDATE activations SET status='revoked' WHERE id=?", (aid,))
        await self.conn.commit()
        return row

    async def due_for_warn(self, hours: int = 48):
        limit = (now() + timedelta(hours=hours)).strftime(FMT)
        cur = await self.conn.execute(
            "SELECT * FROM activations WHERE status='active' AND warned=0 "
            "AND expires_at > ? AND expires_at <= ?",
            (now().strftime(FMT), limit))
        return await cur.fetchall()

    async def mark_warned(self, aid: int):
        await self.conn.execute("UPDATE activations SET warned=1 WHERE id=?", (aid,))
        await self.conn.commit()

    async def renew_candidates(self, renew_cost: int):
        """سلف‌های سکه‌ای که تا ۲۴ آینده تمام می‌شوند و موجودی برای تمدید کافی است."""
        limit = (now() + timedelta(hours=24)).strftime(FMT)
        cur = await self.conn.execute(
            "SELECT a.*, u.balance FROM activations a JOIN users u ON u.user_id=a.user_id "
            "WHERE a.status='active' AND a.plan='coin_1d' AND u.balance>=? "
            "AND a.expires_at > ? AND a.expires_at <= ?",
            (renew_cost, now().strftime(FMT), limit))
        return await cur.fetchall()

    async def set_ping(self, uid: int, ts: str):
        await self.conn.execute(
            "UPDATE activations SET last_ping=? WHERE user_id=? AND status='active'", (ts, uid))
        await self.conn.commit()

    # ---------- stats ----------
    async def stats(self) -> dict:
        today = now().strftime("%Y-%m-%d")

        async def one(q, args=()):
            cur = await self.conn.execute(q, args)
            row = await cur.fetchone()
            return row[0]

        return {
            "users": await one("SELECT COUNT(*) FROM users"),
            "banned": await one("SELECT COUNT(*) FROM users WHERE banned=1"),
            "active_selfs": await one("SELECT COUNT(*) FROM activations WHERE status='active'"),
            "coins": await one("SELECT COALESCE(SUM(balance),0) FROM users"),
            "pending": await one("SELECT COUNT(*) FROM receipts WHERE status='pending'"),
            "today_users": await one("SELECT COUNT(*) FROM users WHERE substr(joined_at,1,10)=?", (today,)),
            "refs": await one("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL"),
        }
