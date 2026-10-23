# -*- coding: utf-8 -*-
"""تست‌های OWNER_SESSIONS — افزودن اکانت خودت از طریق Secret گیت‌هاب.

اجرا:  python tests/test_owner_import.py
بدون شبکه: resolver فیک می‌شود؛ بدون Actions: push خودکار غیرفعال است.
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

# کلید رمزنگاری قطعی قبل از ایمپورت crypto
from cryptography.fernet import Fernet  # noqa: E402
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

PASS = []
FAIL = []


def ok(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name} {extra if not cond else ''}")


print("— ۱) parse_sessions")
from owner_import import (parse_sessions, fp_of, import_owner_sessions,  # noqa: E402
                          run_owner_import)

S1 = "A" * 357
S2 = "B" * 358
S3 = "C" * 356
good = parse_sessions(f"  {S1}\n{S2}, {S3} ;\n{S1}  ")
ok("سه سشن + حذف تکراری", good == [S1, S2, S3])
ok("رد خط کوتاه", S2 not in parse_sessions(f"{S1}\nshort"))
ok("رد خط دارای فاصله داخلی", "x y" not in parse_sessions("x y\n" + S1))
ok("خالی → بدون سشن", parse_sessions("") == [] and parse_sessions(None) == [])
ok("اثر انگشت پایدار", fp_of(S1) == fp_of(S1) and fp_of(S1) != fp_of(S2))

print("— ۲) دیتابیس موقت")
from db import DB  # noqa: E402

tmp = tempfile.mkdtemp()
db = DB(os.path.join(tmp, "star.db"))
await_ = asyncio.new_event_loop()
asyncio.set_event_loop(await_)


class StubBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return True


class Cfg:
    def __init__(self, raw=""):
        self.owner_sessions_raw = raw
        self.api_id = 0
        self.api_hash = ""
        self.admin_id = 999
        self.bot = StubBot()
        self.gh_repo = ""
        self.gh_token = ""
        self.gh_workflow = "selfbot.yml"


cfg = Cfg()
UID1, UID2 = 111111111, 222222222
IDENT = {S1: {"uid": UID1, "username": "ali", "first_name": "Ali", "phone": "+989120000001"},
         S2: {"uid": UID2, "username": "", "first_name": "Sara", "phone": "+989120000002"},
         S3: {"uid": UID1, "username": "ali", "first_name": "Ali", "phone": "+989120000001"}}


async def fake_resolver(_cfg, session):
    r = IDENT.get(session)
    if r is None:
        raise RuntimeError("سشن معتبر نیست یا منقضی شده (not authorized)")
    return dict(r)


async def rows(plan="owner"):
    cur = await db.conn.execute(
        "SELECT * FROM activations WHERE plan=? ORDER BY id", (plan,))
    return await cur.fetchall()


async def main():
    await db.init(cfg.admin_id)

    print("— ۳) افزودن اکانت جدید")
    cfg.owner_sessions_raw = S1
    s = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("یکی اضافه شد", len(s["added"]) == 1 and str(UID1) in s["added"][0], str(s))
    ok("بدون خطا", s["errors"] == [], str(s["errors"]))
    rs = await rows()
    ok("ردیف owner ثبت شد", len(rs) == 1 and rs[0]["status"] == "active")
    ok("پلن owner + اعتبار بلندمدت", rs[0]["plan"] == "owner"
       and int(rs[0]["expires_at"][:4]) >= 2035, rs[0]["expires_at"])
    ok("کاربر ساخته شد", (await db.user(UID1)) is not None)
    ok("خبر فعال‌سازی به اکانت رفت",
       any(c == UID1 for c, _ in cfg.bot.sent), str(cfg.bot.sent))
    phone_dec = rs[0]["phone"]
    from crypto import dec
    ok("شماره رمزنگاری‌شده ذخیره شد", dec(phone_dec) == "+989120000001"
       and phone_dec != "+989120000001")

    print("— ۴) اجرای مجدد بدون تغییر")
    n_users = len(await rows())
    s2 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("بدون تغییر", s2["unchanged"] == 1 and not s2["added"]
       and not s2["updated"] and not s2["revoked"], str(s2))
    ok("ردیف تکراری ساخته نشد", len(await rows()) == n_users)

    print("— ۵) چرخش سشن همان اکانت")
    cfg.owner_sessions_raw = S3  # همان uid1 با سشن تازه
    s3 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("قدیمی لغو شد", s3["revoked"] == 1, str(s3))
    ok("جدید اضافه شد", len(s3["added"]) == 1, str(s3))
    act = [r for r in await rows() if r["status"] == "active"]
    ok("فقط یک ردیف فعال برای uid1", len(act) == 1 and dec(act[0]["session_enc"]) == S3)

    print("— ۶) جایگزینی ردیف غیر-owner همان اکانت")
    await db.add_balance(UID2, 100, "buy", "test")
    coin_aid = await db.add_activation(UID2, "enc-x", "", "coin_1d", 1, "تست")
    cfg.owner_sessions_raw = S2  # uid2
    s4 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("ردیف سکه‌ای همان اکانت لغو شد", s4["updated"] == 1, str(s4))
    cur = await db.conn.execute("SELECT status FROM activations WHERE id=?", (coin_aid,))
    ok("وضعیت ردیف سکه‌ای revoked", (await cur.fetchone())["status"] == "revoked")

    print("— ۷) حذف از Secret → لغو")
    before_ids = [r["id"] for r in await rows()]
    cfg.owner_sessions_raw = ""
    s5 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("فعالِ باقی‌مانده لغو شد", s5["revoked"] == 1, str(s5))
    ok("هیچ ردیف فعالی نماند", all(r["status"] != "active" for r in await rows()))

    print("— ۸) افزودن مجدد همان سشن → فعال‌سازی همان ردیف")
    cfg.owner_sessions_raw = S1
    s6 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("به‌روز (فعال مجدد) شد", s6["updated"] == 1 and not s6["added"], str(s6))
    after_ids = [r["id"] for r in await rows()]
    ok("ردیف تکراری نه — همان id", set(before_ids) == set(after_ids))
    act2 = [r for r in await rows() if r["status"] == "active"]
    ok("دوباره فعال شد", len(act2) == 1 and dec(act2[0]["session_enc"]) == S1)

    print("— ۹) سشن خراب → خطا بدون کرش")
    bad = "Z" * 357
    cfg.owner_sessions_raw = bad
    s7 = await import_owner_sessions(db, cfg, resolver=fake_resolver)
    ok("خطا ثبت شد، کرش نشد", len(s7["errors"]) == 1, str(s7))
    ok("ردیف اضافه نشد", len(await rows()) == len(after_ids))

    print("— ۱۰) گزارش ادمین (run_owner_import)")
    cfg.bot.sent.clear()
    cfg.owner_sessions_raw = S3  # uid1 با سشن تازه → تغییرات دارد
    await run_owner_import(db, cfg)
    ok("گزارش به ادمین رفت",
       any(c == 999 and "OWNER_SESSIONS" in t for c, t in cfg.bot.sent),
       str(cfg.bot.sent))
    cfg.owner_sessions_raw = S3
    cfg.bot.sent.clear()
    await run_owner_import(db, cfg)
    ok("بدون تغییر → گزارشی نمی‌رود", cfg.bot.sent == [])

    await db.close()
    print(f"\nنتیجه: {len(PASS)} ✅ / {FAIL} ❌" if FAIL else
          f"\nنتیجه: {len(PASS)} ✅ — همه سبز")


await_.run_until_complete(main())
await_.close()

if FAIL:
    print(f"FAILURES: {FAIL}")
    sys.exit(1)
