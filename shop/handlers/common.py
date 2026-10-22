# -*- coding: utf-8 -*-
"""حاله‌ها (FSM)، ابزارهای مشترک و هوک GitHub."""
import asyncio
import logging

import aiohttp
from aiogram.fsm.state import State, StatesGroup


class Transfer(StatesGroup):
    wait_to = State()
    wait_amount = State()
    wait_confirm = State()


class Buy(StatesGroup):
    wait_amount = State()
    wait_method = State()
    wait_receipt = State()


class Act(StatesGroup):
    phone = State()
    code = State()
    password = State()


class Support(StatesGroup):
    wait = State()


class AdminFind(StatesGroup):
    user = State()


class AdminAmt(StatesGroup):
    val = State()


class AdminAdd(StatesGroup):
    uid = State()
    days = State()
    session = State()


class AdminSet(StatesGroup):
    val = State()


class AdminFJ(StatesGroup):
    add = State()
    rm = State()


class AdminBC(StatesGroup):
    msg = State()


# کلاینت‌های Telethon در جریان ساخت سشن (توسط uid)
CLIENTS = {}
# خرید در انتظار ساخت سشن: uid -> dict(plan=..., days=..., paid=bool, phone=...)
PENDING = {}

log = logging.getLogger("star_self")


async def maybe_dispatch(cfg):
    """اگر GH_REPO/GH_TOKEN تنظیم شده باشد، یک ران فوری سلف روی GitHub Actions راه می‌اندازد."""
    if not (cfg.gh_repo and cfg.gh_token):
        return
    url = (f"https://api.github.com/repos/{cfg.gh_repo}/"
           f"actions/workflows/{cfg.gh_workflow}/dispatches")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"ref": "main"}, headers={
                "Authorization": f"Bearer {cfg.gh_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }) as resp:
                if resp.status not in (204, 200):
                    body = await resp.text()
                    log.warning("gh dispatch failed %s: %s", resp.status, body[:200])
                else:
                    log.info("gh dispatch OK — self workflow triggered")
    except Exception as e:
        log.warning("gh dispatch error: %s", e)


def fire_and_forget(coro):
    asyncio.get_running_loop().create_task(coro)


async def wallet_text(db, uid: int) -> str:
    """متن کیف پول (مشترک بین wallet و start)."""
    import texts as T
    from utils import fmt_tom

    u = await db.user(uid)
    act = await db.active_of(uid)
    pend = await db.pending_receipt_of(uid)
    price = await db.sint("coin_price", 1000)
    renew = await db.sint("daily_renew", 3)
    bal = u["balance"] if u else 0
    if act:
        self_status = f"✅ فعال تا {act['expires_at'][:16]}"
        can = "✅ دارد" if (act["plan"] == "coin_1d" and bal >= renew) else "—"
    else:
        self_status = "سلف فعال نیست"
        can = "—"
    return T.WALLET.format(
        balance=bal, worth=fmt_tom(bal * price), price=fmt_tom(price),
        self_status=self_status, can_continue=can, pending=1 if pend else 0)
