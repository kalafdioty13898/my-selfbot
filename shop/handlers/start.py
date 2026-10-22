# -*- coding: utf-8 -*-
"""استارت، دعوت، عضویت اجباری و منوی اصلی."""
import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from handlers.common import Transfer, log
from utils import parse_int


def build(cfg, db):
    r = Router()

    async def force_needed(uid: int):
        if not await db.force_on():
            return False
        chs = await db.channels()
        if not chs:
            return False
        for ch in chs:
            try:
                m = await cfg.bot.get_chat_member(ch["id"], uid)
                if m.status not in ("member", "administrator", "creator"):
                    return True
            except Exception:
                return True
        return False

    async def edit_menu(msg):
        try:
            await msg.edit_text(T.WELCOME, reply_markup=K.main_menu())
        except Exception:
            await msg.answer(T.WELCOME, reply_markup=K.main_menu())

    r.edit_menu = edit_menu  # برای ماژول‌های دیگر

    # ---------- /start ----------
    @r.message(CommandStart())
    async def start(m: Message, state: FSMContext, command: CommandObject):
        await state.clear()
        payload = command.args or ""
        ref = None
        if payload.startswith("ref"):
            ref = parse_int(payload[3:])
        res = await db.ensure_user(m.from_user.id, m.from_user.username or "",
                                   m.from_user.first_name or "", ref)
        u = await db.user(m.from_user.id)
        if u["banned"]:
            return await m.answer(T.BANNED)

        if await force_needed(m.from_user.id):
            chs = await db.channels()
            return await m.answer(T.FORCE_JOIN, reply_markup=K.force_join_kb(chs))

        await m.answer(T.WELCOME, reply_markup=K.main_menu())

    # ---------- بررسی عضویت ----------
    @r.callback_query(F.data == "fj_check")
    async def fj_check(cb: CallbackQuery, state: FSMContext):
        if await force_needed(cb.from_user.id):
            await cb.answer(T.FORCE_NOT_YET, show_alert=True)
        else:
            await cb.answer(T.FORCE_OK, show_alert=True)
            await edit_menu(cb.message)

    # ---------- بازگشت به منو ----------
    @r.callback_query(F.data == "menu")
    async def home(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await edit_menu(cb.message)
        await cb.answer()

    # ---------- لغو عمومی FSM ----------
    @r.callback_query(F.data == "cancel")
    async def cancel_flow(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        from handlers import common
        cl = common.CLIENTS.pop(cb.from_user.id, None)
        if cl:
            try:
                await cl.disconnect()
            except Exception:
                pass
        meta = common.PENDING.pop(cb.from_user.id, None)
        # اگر وسط فعال‌سازیِ پرداخت‌شده لغو کرد، سکه‌های پرداختی برگردد
        if meta and meta.get("paid"):
            cost = int(meta.get("amount") or 0) or await db.sint("activation_cost", 15)
            await db.add_balance(cb.from_user.id, cost, "refund", "لغو فعال‌سازی")
            await edit_menu(cb.message)
            return await cb.answer(f"لغو شد؛ {cost} سکه برگشت داده شد ✅")
        await edit_menu(cb.message)
        await cb.answer("لغو شد")

    # ---------- بازگشت به کیف پول ----------
    @r.callback_query(F.data == "cb_wallet_home")
    async def back_wallet(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        from handlers.common import wallet_text
        await cb.message.answer(await wallet_text(db, cb.from_user.id),
                                reply_markup=K.wallet_menu())
        await cb.answer()

    return r
