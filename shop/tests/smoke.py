# -*- coding: utf-8 -*-
"""تست دود ربات فروش star self — بدون اتصال به تلگرام.

اجرا:  python tests/smoke.py
"""
import asyncio
import os
import sys
import tempfile

# مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = []
FAIL = []


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {extra}")


print("— ۱) ایمپورت ماژول‌ها")
try:
    import config, crypto, utils, db, texts, keyboards, api
    import handlers.common as common
    import handlers.start, handlers.wallet, handlers.coins
    import handlers.activate, handlers.tariff, handlers.misc, handlers.admin
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    check("imports", True)
except Exception as e:
    check("imports", False, f"→ {e!r}")
    print("\n❌ ایمپورت شکست خورد — ادامه نمی‌دهم")
    sys.exit(1)


print("— ۲) crypto")
s = "1" * 353 + "AbC"
check("enc/dec roundtrip", crypto.dec(crypto.enc(s)) == s)
check("dec bad token", crypto.dec("garbage!!") == "")


print("— ۳) utils")
check("parse_int latin", utils.parse_int("1,234") == 1234)
check("parse_int persian", utils.parse_int("۴۵") == 45)
check("parse_int bad", utils.parse_int("abc") is None)
check("parse_phone +98", utils.parse_phone("+98 912 345 6789") == "+989123456789")
check("parse_phone local", utils.parse_phone("09123456789") == "+989123456789")
check("parse_phone bad", utils.parse_phone("123") is None)
check("transfer min", utils.transfer_error(10, 100, 0, 20, 10000, 5000) is not None)
check("transfer ok", utils.transfer_error(20, 100, 0, 20, 10000, 5000) is None)
check("transfer cap", utils.transfer_error(6000, 9999, 0, 20, 10000, 5000) is not None)
check("transfer daily", utils.transfer_error(1000, 9999, 4500, 20, 10000, 5000) is not None)
check("transfer poor", utils.transfer_error(500, 100, 0, 20, 10000, 5000) is not None)


print("— ۴) دیتابیس (async)")


async def db_tests():
    tmp = tempfile.mkdtemp()
    d = db.DB(os.path.join(tmp, "t.db"))
    await d.init(admin_id=777)

    # پیش‌فرض‌ها
    check("default coin_price", await d.sint("coin_price") == 1000)
    check("admin wallet 1M", await d.balance(777) == 1_000_000)

    # کاربر + دعوت
    r1 = await d.ensure_user(100, "refuser", "رفیق", None)
    r2 = await d.ensure_user(200, "newbie", "تازه", 100)
    check("new user created", r2["created"] and r2["credited"])
    check("referrer +3", await d.balance(100) == 3)
    check("referee +2", await d.balance(200) == 2)
    r3 = await d.ensure_user(200, "newbie", "تازه", None)
    check("no double credit", not r3["created"])
    check("ref_count", await d.ref_count(100) == 1)

    # شارژ/کسر clamp
    await d.add_balance(200, 100, "admin", "تست")
    check("charge", await d.balance(200) == 102)
    await d.add_balance(200, -9999, "admin", "کسر زیاد")
    check("clamp at 0", await d.balance(200) == 0)

    # انتقال + سقف روزانه
    await d.add_balance(100, 1000, "admin", "شارژ")
    await d.transfer(100, 200, 50)
    check("transfer out", await d.balance(100) == 953)
    check("transfer in", await d.balance(200) == 50)
    check("today sum", await d.today_transfer_sum(100) == 50)

    # رسید
    rid = await d.add_receipt(200, 100, 100000, "file123", "photo")
    check("receipt pending", (await d.pending_receipt_of(200)) is not None)
    await d.decide_receipt(rid, "approved")
    check("receipt decided", (await d.pending_receipt_of(200)) is None)

    # فعال‌سازی
    enc = crypto.enc("x" * 353)
    aid = await d.add_activation(200, enc, "+989120000000", "coin_1d", 1, "note1")
    act = await d.active_of(200)
    check("active_of", act is not None and act["id"] == aid)
    new_exp = await d.extend(200, 7)
    check("extend", new_exp is not None)
    n = await d.expire_due()
    check("expire none now", n == 0)
    # منقضی دستی
    from utils import now, FMT
    from datetime import timedelta
    past = (now() - timedelta(hours=2)).strftime(FMT)
    await d.conn.execute("UPDATE activations SET expires_at=? WHERE id=?", (past, aid))
    await d.conn.commit()
    check("expire_due", await d.expire_due() == 1)
    check("no active after expire", (await d.active_of(200)) is None)
    check("revoke", (await d.revoke(aid))["status"] in ("expired",))

    # تمدید خودکار
    aid2 = await d.add_activation(100, enc, "+989110000000", "coin_1d", 1, "")
    from utils import now as _n
    soon = (_n() + timedelta(hours=10)).strftime(FMT)
    await d.conn.execute("UPDATE activations SET expires_at=? WHERE id=?", (soon, aid2))
    await d.conn.commit()
    cands = await d.renew_candidates(3)
    check("renew candidate", len(cands) == 1 and cands[0]["user_id"] == 100)
    await d.set_ping(100, now().strftime(FMT))
    check("set_ping", (await d.active_of(100))["last_ping"] != "")

    # تنظیمات و کانال‌ها
    await d.sset("card_number", "6037991111111111")
    check("sset", await d.sget("card_number") == "6037991111111111")
    await d.set_channels([{"id": -100123, "title": "چنل", "link": "https://t.me/x"}])
    check("channels json", (await d.channels())[0]["id"] == -100123)
    await d.sset("force_on", "1")
    check("force_on", await d.force_on())

    # آمار
    s = await d.stats()
    check("stats keys", {"users", "active_selfs", "coins", "pending"} <= set(s.keys()))

    # تراکنش‌ها
    txs = await d.last_transactions(100, 5)
    check("last_transactions", len(txs) >= 2)

    await d.close()

asyncio.run(db_tests())


print("— ۵) کیبوردها")
mm = keyboards.main_menu()
n_btn = sum(len(row) for row in mm.inline_keyboard)
check("main menu 10 buttons", n_btn == 10, f"→ {n_btn}")
for name, kbs in [
    ("wallet", keyboards.wallet_menu()), ("act_confirm", keyboards.act_confirm()),
    ("buy_method", keyboards.buy_method()), ("tariff", keyboards.tariff_menu("۱۵۰٬۰۰۰", "۲۵۰٬۰۰۰")),
    ("ref", keyboards.ref_menu()), ("admin", keyboards.admin_menu()),
    ("settings", keyboards.settings_kb()), ("user_card", keyboards.user_card_kb(1)),
    ("vault", keyboards.vault_kb([], 0, 1)),
]:
    check(f"kb {name}", isinstance(kbs, InlineKB := type(mm)) and len(kbs.inline_keyboard) > 0)

print("— ۶) متن‌ها (format)")
try:
    dummy = dict(name="علی", balance=10, worth="10,000", price="1,000", self_status="—",
                 can_continue="—", pending=0, min_t=20, max_t=10000, cap=5000,
                 uname="@x", uid=1, amount=5, cost=15, toman="10,000", coins=10,
                 card="6037", owner="x", rows="—", link="http://x", reward=3, gift=2,
                 count=0, earned=0, status="—", expires="—", plan="—", ping="—",
                 renew=3, label="۲ ماهه", note="", days=1, act=15, min_buy=30,
                 price2=1000, n=0, page=1, pages=1, aid=1, phone="—",
                 session="x", err="x", ok=1, fail=0, key="k", val="v",
                 on="✅", list="—", users=0, banned=0, today_users=0,
                 active_selfs=0, refs=0, fname="—", ban="—", self_txt="—",
                 utxt="—", uname2="—", sender="—", sid=1, username="x")
    for tname in ["WALLET", "TRANSFER_1", "TRANSFER_2", "TRANSFER_CONFIRM", "BUY",
                  "PAY_METHOD", "RECEIPT", "REF", "REF_STATS", "HEALTH_OK", "TARIFF",
                  "PLAN_MSG", "PLAN_NO_BAL", "PLAN_DONE", "ACTIVATED", "RENEW_AUTO",
                  "AD_STATS", "AD_USER_CARD", "AD_VAULT_HEAD", "AD_FORCE", "TX_LIST",
                  "AD_BCAST_DONE", "ACT_ASK", "NO_BALANCE", "TRANSFER_DONE", "TRANSFER_RECV",
                  "RECEIPT_SENT", "RECEIPT_OK"]:
        getattr(texts, tname).format(**dummy)
    check("all texts format", True)
except KeyError as e:
    check("all texts format", False, f"→ missing key {e}")

print("— ۷) API و روتینگ")
app = api.build_api(
    type("C", (), {"shop_key": "k", "bot_username": "b"})(), None)
check("aiohttp app", app is not None)


class FakeCfg:
    admin_id = 777
    bot = None
    api_id = 1
    api_hash = "h"
    bot_username = "st4r_self_bot"
    gh_repo = ""
    gh_token = ""
    gh_workflow = "selfbot.yml"


async def router_tests():
    tmp = tempfile.mkdtemp()
    d = db.DB(os.path.join(tmp, "r.db"))
    await d.init(777)
    cfg = FakeCfg()
    dp = Dispatcher(storage=MemoryStorage())
    for mod in (handlers.start, handlers.wallet, handlers.coins,
                handlers.activate, handlers.tariff, handlers.misc, handlers.admin):
        dp.include_router(mod.build(cfg, d))
    check("routers registered", len(dp.sub_routers) == 7)
    await d.close()

asyncio.run(router_tests())


print()
print(f"═══ نتیجه: {len(PASS)} پاس / {len(FAIL)} شکست ═══")
if FAIL:
    print("شکست‌ها:", FAIL)
    sys.exit(1)
print("🎉 همه تست‌های دود پاس شدند")
