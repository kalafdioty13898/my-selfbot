# -*- coding: utf-8 -*-
"""کیف پول، انتقال سکه (۲ مرحله‌ای) و تراکنش‌ها."""
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from handlers.common import Transfer
from utils import parse_int, transfer_error, fmt_tom, esc, now


def build(cfg, db):
    r = Router()

    async def render_wallet(msg, uid=None):
        uid = uid or msg.chat.id
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
        await msg.answer(T.WALLET.format(
            balance=bal, worth=fmt_tom(bal * price), price=fmt_tom(price),
            self_status=self_status, can_continue=can,
            pending=1 if pend else 0), reply_markup=K.wallet_menu())

    r.render_wallet = render_wallet

    # ---------- کیف پول ----------
    @r.callback_query(F.data == "cb_wallet")
    async def wallet(cb: CallbackQuery, state: FSMContext):
        await render_wallet(cb.message, cb.from_user.id)
        await cb.answer()

    # ---------- تراکنش‌ها ----------
    @r.callback_query(F.data == "tx")
    async def tx(cb: CallbackQuery):
        rows = await db.last_transactions(cb.from_user.id, 10)
        if not rows:
            await cb.message.answer(T.TX_EMPTY, reply_markup=K.back_menu("cb_wallet_home"))
        else:
            body = []
            for x in rows:
                label = T.TX_ROWS.get(x["type"], x["type"])
                sign = "+" if (x["amount"] or 0) > 0 else ""
                body.append(f"▪️ {label}: {sign}{x['amount']} سکه — {(x['created_at'] or '')[:16]}")
            await cb.message.answer(T.TX_LIST.format(rows="\n".join(body)),
                                    reply_markup=K.back_menu("cb_wallet_home"))
        await cb.answer()

    # ---------- انتقال سکه: مرحله ۱ ----------
    @r.callback_query(F.data == "cb_transfer")
    async def tr1(cb: CallbackQuery, state: FSMContext):
        from handlers.common import abort_pending
        await abort_pending(db, state, cb.from_user.id)  # خروج امن از جریان فعال‌سازی
        await state.set_state(Transfer.wait_to)
        await cb.message.answer(T.TRANSFER_1.format(
            min_t=await db.sint("min_transfer", 20),
            max_t=await db.sint("max_transfer", 10000),
            cap=await db.sint("daily_cap", 5000)),
            reply_markup=K.support_kb())  # فقط دکمه لغو
        await cb.answer()

    @r.message(Transfer.wait_to)
    async def tr_to(m: Message, state: FSMContext):
        raw = (m.text or "").strip()
        if raw.startswith("@") or (not raw.isdigit() and raw.isalnum()):
            dst = await db.user_by_username(raw)
        else:
            uid = parse_int(raw)
            dst = await db.user(uid) if uid else None
        if not dst:
            return await m.answer(T.AD_USER_NF)
        if dst["user_id"] == m.from_user.id:
            return await m.answer("⚠️ نمی‌توانی به خودت انتقال بدهی!")
        if dst["banned"]:
            return await m.answer("⚠️ این کاربر بن شده است.")
        await state.update_data(dst_id=dst["user_id"],
                                dst_un=f"@{dst['username']}" if dst["username"] else dst["first_name"])
        await state.set_state(Transfer.wait_amount)
        await m.answer(T.TRANSFER_2.format(
            uname=esc(f"@{dst['username']}" if dst["username"] else dst["first_name"]),
            uid=dst["user_id"],
            balance=await db.balance(m.from_user.id),
            min_t=await db.sint("min_transfer", 20),
            max_t=await db.sint("max_transfer", 10000),
            cap=await db.sint("daily_cap", 5000)),
            reply_markup=K.support_kb())

    @r.message(Transfer.wait_amount)
    async def tr_amount(m: Message, state: FSMContext):
        amount = parse_int(m.text)
        bal = await db.balance(m.from_user.id)
        err = transfer_error(amount, bal, await db.today_transfer_sum(m.from_user.id),
                             await db.sint("min_transfer", 20),
                             await db.sint("max_transfer", 10000),
                             await db.sint("daily_cap", 5000))
        if err:
            return await m.answer(err)
        data = await state.get_data()
        await state.update_data(amount=amount)
        await state.set_state(Transfer.wait_confirm)
        await m.answer(T.TRANSFER_CONFIRM.format(
            uname=data["dst_un"], uid=data["dst_id"], amount=amount, balance=bal),
            reply_markup=K.transfer_confirm())

    @r.callback_query(F.data == "tr_yes", Transfer.wait_confirm)
    async def tr_go(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        amount = data.get("amount", 0)
        dst_id = data.get("dst_id")
        bal = await db.balance(cb.from_user.id)
        if amount <= 0 or not dst_id:
            await cb.answer("خطا! دوباره تلاش کن.", show_alert=True)
            return
        if bal < amount:
            await cb.answer(f"موجودی کافی نیست ({bal} سکه).", show_alert=True)
            await state.clear()
            return
        await db.transfer(cb.from_user.id, dst_id, amount)
        await state.clear()
        try:
            await cfg.bot.send_message(
                dst_id, T.TRANSFER_RECV.format(
                    amount=amount, sender=cb.from_user.first_name or "",
                    sid=cb.from_user.id, balance=await db.balance(dst_id)))
        except Exception:
            pass
        await cb.message.edit_text(T.TRANSFER_DONE.format(
            amount=amount, uname=data["dst_un"], uid=dst_id),
            reply_markup=K.back_menu("cb_wallet_home"))
        await cb.answer("انجام شد ✅")

    return r
