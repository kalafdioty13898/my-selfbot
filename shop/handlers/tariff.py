# -*- coding: utf-8 -*-
"""تعرفه سلف: پلن‌های ۲ ماهه / ۴ ماهه / رایگان (زیرمجموعه‌گیری)."""
import math

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from handlers.common import PENDING, maybe_dispatch, fire_and_forget
from utils import fmt_tom, PLAN_LABELS


def build(cfg, db):
    r = Router()

    async def render_ref(msg, uid):
        u = await db.user(uid)
        link = f"https://t.me/{cfg.bot_username}?start=ref{uid}"
        count = await db.ref_count(uid)
        earned = await db.ref_earned(uid)
        await msg.answer(T.REF.format(
            link=link,
            reward=await db.sint("ref_reward", 3),
            gift=await db.sint("ref_gift", 2),
            count=count, earned=earned),
            reply_markup=K.ref_menu())

    r.render_ref = render_ref

    @r.callback_query(F.data == "cb_ref")
    async def ref(cb: CallbackQuery):
        await render_ref(cb.message, cb.from_user.id)
        await cb.answer()

    @r.callback_query(F.data == "cb_refstat")
    async def refstat(cb: CallbackQuery):
        uid = cb.from_user.id
        u = await db.user(uid)
        price = await db.sint("coin_price", 1000)
        count = await db.ref_count(uid)
        earned = await db.ref_earned(uid)
        await cb.message.answer(T.REF_STATS.format(
            balance=u["balance"], worth=fmt_tom(u["balance"] * price),
            count=count, earned=earned, reward=await db.sint("ref_reward", 3)),
            reply_markup=K.ref_stats_back())
        await cb.answer()

    # ---------- تعرفه ----------
    @r.callback_query(F.data == "cb_tariff")
    async def tariff(cb: CallbackQuery):
        p2 = fmt_tom(await db.sint("plan_2m_price", 150000))
        p4 = fmt_tom(await db.sint("plan_4m_price", 250000))
        await cb.message.answer(T.TARIFF.format(renew=await db.sint("daily_renew", 3)),
                                reply_markup=K.tariff_menu(p2, p4))
        await cb.answer()

    @r.callback_query(F.data == "tar_2m")
    async def tar2(cb: CallbackQuery):
        await buy_plan(cb, "plan_2m", await db.sint("plan_2m_price", 150000), 60)

    @r.callback_query(F.data == "tar_4m")
    async def tar4(cb: CallbackQuery):
        await buy_plan(cb, "plan_4m", await db.sint("plan_4m_price", 250000), 120)

    @r.callback_query(F.data == "tar_free")
    async def tarfree(cb: CallbackQuery):
        await render_ref(cb.message, cb.from_user.id)
        await cb.answer()

    async def buy_plan(cb: CallbackQuery, plan: str, toman_price: int, days: int):
        uid = cb.from_user.id
        price = max(1, await db.sint("coin_price", 1000))
        coins_needed = math.ceil(toman_price / price)
        label = PLAN_LABELS.get(plan, plan)
        bal = await db.balance(uid)
        if bal < coins_needed:
            await cb.message.answer(T.PLAN_NO_BAL.format(
                label=label, coins=coins_needed, balance=bal),
                reply_markup=K.need_coins())
            return await cb.answer()
        await cb.message.answer(T.PLAN_MSG.format(
            label=label, coins=coins_needed, balance=bal),
            reply_markup=K.plan_confirm(plan))
        await cb.answer()

    # تأیید نهایی خرید پلن — plan در callback: tard_plan_2m
    @r.callback_query(F.data.startswith("tard_"))
    async def plan_go(cb: CallbackQuery, state: FSMContext):
        plan = cb.data[5:]
        uid = cb.from_user.id
        if plan == "plan_2m":
            toman_price, days = await db.sint("plan_2m_price", 150000), 60
        elif plan == "plan_4m":
            toman_price, days = await db.sint("plan_4m_price", 250000), 120
        else:
            return await cb.answer("پلن نامعتبر", show_alert=True)
        price = max(1, await db.sint("coin_price", 1000))
        coins_needed = math.ceil(toman_price / price)
        label = PLAN_LABELS.get(plan, plan)
        bal = await db.balance(uid)
        if bal < coins_needed:
            await cb.answer(f"موجودی کافی نیست ({bal} سکه).", show_alert=True)
            return await cb.message.answer(T.PLAN_NO_BAL.format(
                label=label, coins=coins_needed, balance=bal),
                reply_markup=K.need_coins())
        await db.add_balance(uid, -coins_needed, "plan", f"خرید {label}")
        act = await db.active_of(uid)
        if act:
            # تمدید سلف موجود — نیازی به سشن جدید نیست
            new_exp = await db.extend(uid, days)
            fire_and_forget(maybe_dispatch(cfg))
            await cb.message.answer(T.PLAN_DONE.format(
                label=label, expires=new_exp[:16]),
                reply_markup=K.back_menu("menu"))
        else:
            # سشن ندارد → بعد از پرداخت، جریان ساخت سشن
            PENDING[uid] = {"plan": plan, "days": days, "paid": True}
            from handlers.common import Act
            await state.set_state(Act.phone)
            await cb.message.answer(T.SESSION_PHONE)
        await cb.answer("پرداخت شد ✅")

    return r
