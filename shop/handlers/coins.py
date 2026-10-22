# -*- coding: utf-8 -*-
"""خرید سکه با کارت‌به‌کارت و رسید."""
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from handlers.common import Buy
from utils import parse_int, fmt_tom


def build(cfg, db):
    r = Router()

    @r.callback_query(F.data == "cb_buy")
    async def buy(cb: CallbackQuery, state: FSMContext):
        from handlers.common import abort_pending
        await abort_pending(db, state, cb.from_user.id)  # خروج امن از جریان فعال‌سازی
        if await db.pending_receipt_of(cb.from_user.id):
            await cb.answer(T.RECEIPT_DUP, show_alert=True)
            return
        await state.set_state(Buy.wait_amount)
        await cb.message.answer(T.BUY.format(
            price=fmt_tom(await db.sint("coin_price", 1000)),
            min_buy=await db.sint("min_buy", 30),
            act=await db.sint("activation_cost", 15),
            days=await db.sint("initial_days", 1),
            renew=await db.sint("daily_renew", 3)),
            reply_markup=K.support_kb())
        await cb.answer()

    @r.message(Buy.wait_amount)
    async def buy_amount(m: Message, state: FSMContext):
        amount = parse_int(m.text)
        min_buy = await db.sint("min_buy", 30)
        if amount is None or amount < min_buy:
            return await m.answer(T.BUY_MIN.format(min_buy=min_buy))
        toman = amount * await db.sint("coin_price", 1000)
        await state.update_data(coins=amount, toman=toman)
        await state.set_state(Buy.wait_method)
        await m.answer(T.PAY_METHOD.format(toman=fmt_tom(toman), coins=amount),
                       reply_markup=K.buy_method())

    @r.callback_query(F.data == "buy_card", Buy.wait_method)
    async def buy_card(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get("toman") or not data.get("coins"):
            await state.set_state(Buy.wait_amount)
            await cb.message.answer("⌛ مدت‌ زمان گذشته؛ دوباره بگو چند سکه می‌خری (عدد بفرست).")
            return await cb.answer()
        await state.set_state(Buy.wait_receipt)
        await cb.message.answer(T.RECEIPT.format(
            toman=fmt_tom(data["toman"]), coins=data["coins"],
            card=await db.sget("card_number", "-"),
            owner=await db.sget("card_owner", "-")))
        await cb.answer()

    @r.message(Buy.wait_receipt, F.photo)
    async def receipt_photo(m: Message, state: FSMContext):
        await save_receipt(m, state, m.photo[-1].file_id, "photo")

    @r.message(Buy.wait_receipt, F.document)
    async def receipt_doc(m: Message, state: FSMContext):
        await save_receipt(m, state, m.document.file_id, "document")

    @r.message(Buy.wait_receipt)
    async def receipt_other(m: Message, state: FSMContext):
        await m.answer("📸 لطفاً تصویر یا PDF رسید را ارسال کن.")

    async def save_receipt(m: Message, state: FSMContext, file_id: str, ftype: str):
        data = await state.get_data()
        if not data.get("coins") or not data.get("toman"):
            await state.set_state(Buy.wait_amount)
            return await m.answer("⌛ جریان خرید منقضی شد؛ دوباره بگو چند سکه می‌خری (عدد بفرست).")
        rid = await db.add_receipt(m.from_user.id, data["coins"], data["toman"], file_id, ftype)
        await state.clear()
        # اطلاع به ادمین
        try:
            await cfg.bot.send_message(
                cfg.admin_id,
                f"🧾 رسید جدید #{rid}\n👤 🆔 {m.from_user.id} @{m.from_user.username}\n"
                f"🪙 {data['coins']} سکه | 💳 {fmt_tom(data['toman'])} تومان",
                reply_markup=K.receipt_kb(rid))
            await cfg.bot.send_photo(cfg.admin_id, file_id) if ftype == "photo" else \
                await cfg.bot.send_document(cfg.admin_id, file_id)
        except Exception:
            pass
        await m.answer(T.RECEIPT_SENT.format(coins=data["coins"], toman=fmt_tom(data["toman"])),
                       reply_markup=K.after_receipt())

    return r
